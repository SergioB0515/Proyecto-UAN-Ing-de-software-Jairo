"""Motor de liquidación del impuesto de renta de personas naturales residentes.

Qué hace
--------
Toma los insumos depurados de un contribuyente y produce el borrador de la
liquidación: renta líquida por cédula, impuesto según la tabla del art. 241,
ganancias ocasionales, descuentos, anticipo y saldo a pagar o a favor.

Qué NO hace
-----------
No decide. Cada renglón sale con la fórmula que lo produjo y la norma que lo
respalda para que el contador lo revise y lo ajuste. La responsabilidad de la
declaración es del contribuyente y del contador que la firma (art. 581 ET);
este módulo es una herramienta de apoyo y los resultados deben validarse antes
de transcribirlos a la declaración.

Decisiones de diseño
--------------------
1. **Sin base de datos y sin estado.** Funciones puras sobre dataclasses. Así
   se puede probar el cálculo con cifras de papel sin montar Postgres, que es
   la única forma de tener confianza en aritmética tributaria.
2. **Decimal, no float.** Todo importe es Decimal. El redondeo se hace de forma
   explícita y solo donde la norma lo manda.
3. **Parámetros inyectados.** El motor no conoce ningún número del Estatuto:
   los recibe de `tablas_oficiales.ParametrosAnuales`. Un año nuevo o una
   reforma se resuelven cambiando datos, no lógica.
4. **Trazabilidad obligatoria.** Ningún valor llega al resultado sin su fórmula
   y su fuente legal. Es lo que diferencia una herramienta auditable de una
   caja negra, y es el requisito que hace el producto defendible ante una
   revisión de la DIAN.
"""

from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple

from ..parametros.tablas_oficiales import ParametrosAnuales, TramoTarifa
from .cedula_general import (
    CAPITAL,
    DEDUCCION_OTRA,
    DEDUCCION_VIVIENDA,
    EXENTA_AFC,
    EXENTA_OTRA,
    NO_LABORAL,
    SIN_VINCULO,
    SUBCEDULAS,
    TRABAJO,
    casillas_de,
)
from .cedula_general import depurar as depurar_cedula_general
from .formulario_210 import nota_de_numeracion
from .calculos_empresariales import (
    ActivoDepreciable,
    InsumosBancarizacion,
    InsumosComparacionPatrimonial,
    PerdidaCompensable,
    calcular_bancarizacion,
    calcular_comparacion_patrimonial,
    calcular_compensacion_perdidas,
    calcular_depreciacion,
)

CERO = Decimal("0")
_CENTAVO = Decimal("0.01")
_MIL = Decimal("1000")

_NOMBRE_SUBCEDULA = {
    TRABAJO: "rentas de trabajo",
    SIN_VINCULO: "rentas de trabajo sin vínculo laboral",
    CAPITAL: "rentas de capital",
    NO_LABORAL: "rentas no laborales",
}


# ---------------------------------------------------------------------------
# Utilidades de redondeo
# ---------------------------------------------------------------------------


def redondear_pesos(valor: Decimal) -> Decimal:
    """Redondea a dos decimales para los cálculos intermedios."""
    return valor.quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def aproximar_al_multiplo_de_mil(valor: Decimal) -> Decimal:
    """Aproxima al múltiplo de mil más cercano, como exige el art. 577 ET.

    Los valores de la declaración se presentan aproximados al múltiplo de mil
    más cercano. Se aplica únicamente al renglón que se transcribe, nunca a los
    cálculos intermedios: aproximar antes de operar desplaza el resultado.
    """
    return (valor / _MIL).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * _MIL


def _no_negativo(valor: Decimal) -> Decimal:
    return valor if valor > CERO else CERO


def porcentaje(fraccion: Decimal) -> str:
    """Formatea una fracción como porcentaje legible: 0.40 → «40».

    No se usa `Decimal.normalize()` porque convierte los múltiplos de diez a
    notación científica: `Decimal("40.00").normalize()` devuelve `4E+1`, y la
    fórmula le mostraría «4E+1 %» al contador. Se quitan los ceros de la parte
    decimal a mano y se conservan los decimales que importan (2,22 % del
    art. 137).
    """
    texto = f"{(fraccion * 100):f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


# ---------------------------------------------------------------------------
# Insumos
# ---------------------------------------------------------------------------


@dataclass
class ConceptoDepuracion:
    """Una deducción o renta exenta solicitada, con su tratamiento frente al límite.

    `sujeto_a_limite_general` distingue los conceptos que caen bajo el 40 % /
    1.340 UVT del art. 336 num. 3 de los que la ley dejó por fuera (la
    deducción por dependientes y el 1 % de compras del num. 5). Confundirlos es
    el error de liquidación más común y cambia el impuesto de forma material.
    """

    nombre: str
    valor: Decimal
    sujeto_a_limite_general: bool = True
    fuente_legal: str = ""
    # Código del catálogo de plantillas. Es lo que permite al motor saber qué
    # tope propio le corresponde al concepto. Sin él no se aplica ninguno:
    # para una deducción escrita a mano, el motor no puede adivinar su techo.
    codigo_tope: Optional[str] = None
    # Columna del formulario 210 a la que se imputa. El límite del art. 336
    # num. 3 es uno solo para toda la cédula general, pero el formulario pide
    # las exentas y deducciones separadas por subcédula (casillas 41, 53, 69 y
    # 86), así que cada concepto tiene que saber a cuál pertenece.
    #
    # `None` significa que el contador no la fijó: el motor la reparte entre
    # las columnas con renta líquida, en el orden del formulario. Fijarla es
    # mejor cuando se sabe, porque la imputación cambia en qué casilla aparece.
    subcedula: Optional[str] = None
    # Fila del formulario. Los aportes voluntarios a AFC, FVP y AVC tienen
    # casilla propia (35, 47, 63, 80), separada de las demás rentas exentas, y
    # los intereses de vivienda también (38, 50, 66, 83).
    tipo: str = EXENTA_OTRA


@dataclass
class RentasDeTrabajo:
    """Rentas de trabajo de la cédula general (art. 335 ET)."""

    ingresos_brutos: Decimal = CERO
    aportes_obligatorios_salud: Decimal = CERO
    aportes_obligatorios_pension: Decimal = CERO
    otros_ingresos_no_constitutivos: Decimal = CERO

    # Honorarios y compensaciones sin vínculo laboral. El art. 336 num. 4 obliga
    # a elegir: o se restan costos y gastos, o se toma la renta exenta del
    # art. 206 num. 10. No se pueden usar las dos.
    ingresos_sin_vinculo_laboral: Decimal = CERO
    costos_y_gastos_sin_vinculo_laboral: Decimal = CERO
    opta_por_costos_y_gastos: bool = False

    @property
    def total_ingresos(self) -> Decimal:
        return self.ingresos_brutos + self.ingresos_sin_vinculo_laboral

    @property
    def total_incrngo(self) -> Decimal:
        return (
            self.aportes_obligatorios_salud
            + self.aportes_obligatorios_pension
            + self.otros_ingresos_no_constitutivos
        )


@dataclass
class RentasPorSubcedula:
    """Rentas de capital o no laborales (arts. 338 y 340 ET).

    `costo_de_ventas` va aparte de `costos_y_gastos` porque lo calcula el
    kardex del módulo de inventario y no lo digita el contador: separarlo deja
    ver en el borrador de dónde salió cada cifra.
    """

    ingresos_brutos: Decimal = CERO
    # Devoluciones, rebajas y descuentos en ventas (casilla 75 del 210). Solo
    # las rentas no laborales tienen esta fila en el formulario.
    devoluciones: Decimal = CERO
    ingresos_no_constitutivos: Decimal = CERO
    costos_y_gastos: Decimal = CERO
    costo_de_ventas: Decimal = CERO
    depreciacion: Decimal = CERO
    # Costos que se restaron en los libros pero que la ley no acepta, hoy solo
    # los pagos en efectivo que exceden el límite del art. 771-5. Se llevan en
    # un campo propio para no alterar las cifras que vienen del kardex ni de la
    # tabla de depreciación: así la casilla de costos del formulario queda con
    # el valor procedente exacto y el origen de cada cifra sigue siendo visible.
    costos_no_procedentes: Decimal = CERO

    @property
    def total_costos(self) -> Decimal:
        return _no_negativo(
            self.costos_y_gastos
            + self.costo_de_ventas
            + self.depreciacion
            - self.costos_no_procedentes
        )


@dataclass
class Pensiones:
    """Cédula de pensiones (art. 337 ET)."""

    ingresos_brutos: Decimal = CERO
    ingresos_no_constitutivos: Decimal = CERO
    meses_causados: int = 12


@dataclass
class Dividendos:
    """Dividendos y participaciones de residentes.

    Los valores se toman del certificado que expide la sociedad, incluida la
    retención.

    A los gravados (par. 2 del art. 49) se les aplica primero la tarifa del art.
    240 —casilla 118— y solo el remanente entra a la tabla del art. 241. La
    tarifa general es del 35 %; el art. 240 tiene tarifas diferenciales para
    ciertas sociedades y el servicio de la DIAN deja digitarla, así que se
    puede fijar aquí cuando el certificado indique otra.
    """

    no_gravados: Decimal = CERO
    gravados: Decimal = CERO
    retencion_practicada: Decimal = CERO
    tarifa_gravados: Optional[Decimal] = None


@dataclass
class GananciasOcasionales:
    """Ganancias ocasionales (arts. 299 y siguientes ET)."""

    ingresos: Decimal = CERO
    costos: Decimal = CERO
    ganancia_exenta: Decimal = CERO          # p. ej. venta de vivienda, art. 311-1
    loterias_rifas_apuestas: Decimal = CERO  # tarifa propia, art. 317
    retenciones: Decimal = CERO


@dataclass
class Patrimonio:
    patrimonio_bruto: Decimal = CERO
    deudas: Decimal = CERO

    @property
    def patrimonio_liquido(self) -> Decimal:
        return self.patrimonio_bruto - self.deudas


@dataclass
class InsumosLiquidacion:
    anio_gravable: int
    trabajo: RentasDeTrabajo = field(default_factory=RentasDeTrabajo)
    capital: RentasPorSubcedula = field(default_factory=RentasPorSubcedula)
    no_laborales: RentasPorSubcedula = field(default_factory=RentasPorSubcedula)
    pensiones: Pensiones = field(default_factory=Pensiones)
    dividendos: Dividendos = field(default_factory=Dividendos)
    ganancias_ocasionales: GananciasOcasionales = field(
        default_factory=GananciasOcasionales
    )
    patrimonio: Patrimonio = field(default_factory=Patrimonio)

    conceptos_depuracion: List[ConceptoDepuracion] = field(default_factory=list)
    numero_dependientes: int = 0
    compras_con_factura_electronica: Decimal = CERO

    renta_presuntiva: Decimal = CERO
    retenciones_en_la_fuente: Decimal = CERO
    otros_descuentos_tributarios: Decimal = CERO
    anticipo_pagado_anio_anterior: Decimal = CERO
    saldo_a_favor_anio_anterior: Decimal = CERO
    # Sanciones que el contribuyente se liquida a sí mismo (casilla 135), hoy la
    # de extemporaneidad. El motor no la calcula: depende de fechas y del
    # calendario, y esta función no mira el reloj. La calcula `sanciones.py`
    # y llega aquí ya resuelta, con su fórmula.
    sanciones: Decimal = CERO
    formula_sanciones: str = ""
    anios_declarando: int = 3  # 1 = primer año, 2 = segundo, 3 o más = régimen pleno

    # Parte empresarial
    activos_depreciables: List[ActivoDepreciable] = field(default_factory=list)
    bancarizacion: InsumosBancarizacion = field(default_factory=InsumosBancarizacion)
    perdidas_compensables: List[PerdidaCompensable] = field(default_factory=list)
    comparacion_patrimonial: InsumosComparacionPatrimonial = field(
        default_factory=InsumosComparacionPatrimonial
    )

    # Anticipo: "DIRECTO", "PROMEDIO" o "MENOR" (calcula los dos y toma el menor).
    metodo_anticipo: str = "DIRECTO"
    impuesto_neto_anio_anterior: Decimal = CERO

    # Subcédula a la que se imputa la depreciación. Depende de la actividad que
    # produce el activo, así que la decide el contador, no el motor.
    cedula_depreciacion: str = "NO_LABORAL"


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass
class Renglon:
    """Un valor de la liquidación con su rastro completo."""

    codigo: str
    nombre: str
    valor: Decimal
    formula: str = ""
    fuente_legal: str = ""
    # Número de casilla del formulario 210 cuando el renglón corresponde a una.
    # Es lo que permite imprimir la grilla sin que nadie tenga que mantener un
    # segundo mapa de códigos a casillas.
    casilla: Optional[int] = None

    @property
    def valor_declarable(self) -> Decimal:
        """El valor como se transcribe a la declaración (art. 577 ET)."""
        return aproximar_al_multiplo_de_mil(self.valor)


@dataclass
class Liquidacion:
    anio_gravable: int
    uvt: Decimal
    regimen: str
    renglones: List[Renglon] = field(default_factory=list)
    diagnosticos: List[str] = field(default_factory=list)
    notas: List[str] = field(default_factory=list)
    # Casillas del formulario que no llevan valor sino una marca (hoy, la 140).
    casillas_marcadas: List[int] = field(default_factory=list)

    def valor(self, codigo: str) -> Decimal:
        for renglon in self.renglones:
            if renglon.codigo == codigo:
                return renglon.valor
        return CERO


class AnioGravableNoSoportadoError(Exception):
    """El año pedido no tiene parámetros cargados.

    Se prefiere fallar a liquidar con los parámetros de otro año: una cifra
    equivocada que parece correcta es peor que un error visible.
    """


# ---------------------------------------------------------------------------
# Tabla de tarifas
# ---------------------------------------------------------------------------


def aplicar_tabla(
    base_pesos: Decimal, tabla: Tuple[TramoTarifa, ...], uvt: Decimal
) -> Tuple[Decimal, str, Optional[TramoTarifa]]:
    """Aplica una tabla marginal en UVT a una base en pesos.

    Devuelve el impuesto en pesos, la fórmula aplicada y el tramo usado. El
    cálculo se hace en UVT, como está escrita la tabla, y solo al final se
    convierte a pesos.
    """
    if base_pesos <= CERO:
        return CERO, "Base gravable igual o menor a cero: impuesto 0", None

    base_uvt = base_pesos / uvt
    tramo = next((t for t in tabla if t.contiene(base_uvt)), None)
    if tramo is None:
        # Solo ocurre si la base cae en el primer tramo exento (0 a 1.090 UVT).
        return (
            CERO,
            f"Base de {base_uvt.quantize(_CENTAVO)} UVT en el tramo exento: impuesto 0",
            tabla[0],
        )

    exceso_uvt = base_uvt - tramo.desde_uvt
    impuesto_uvt = tramo.impuesto_acumulado_uvt + exceso_uvt * tramo.tarifa_marginal
    impuesto = redondear_pesos(impuesto_uvt * uvt)

    formula = (
        f"Base {base_uvt.quantize(_CENTAVO)} UVT en el tramo "
        f"{tramo.desde_uvt}–{tramo.hasta_uvt or 'en adelante'} UVT: "
        f"{tramo.impuesto_acumulado_uvt} UVT + "
        f"{porcentaje(tramo.tarifa_marginal)}% × "
        f"{exceso_uvt.quantize(_CENTAVO)} UVT = "
        f"{impuesto_uvt.quantize(_CENTAVO)} UVT × ${uvt}"
    )
    return impuesto, formula, tramo


# ---------------------------------------------------------------------------
# Depuración de la cédula general (art. 336 ET)
# ---------------------------------------------------------------------------


def _renta_exenta_trabajo(
    insumos: InsumosLiquidacion,
    parametros: ParametrosAnuales,
    otras_restas_de_trabajo: Decimal,
) -> Tuple[Decimal, str]:
    """Calcula la renta exenta del 25 % de las rentas de trabajo (art. 206 num. 10).

    Se calcula sobre el subtotal que queda después de restar los ingresos no
    constitutivos y las demás deducciones y rentas exentas imputables, no sobre
    el ingreso bruto, y queda topada en 790 UVT.

    Quien tiene honorarios sin vínculo laboral y optó por restar costos y gastos
    pierde esta exención (art. 336 num. 4). El motor respeta esa exclusión.
    """
    trabajo = insumos.trabajo
    limite = parametros.renta_exenta_trabajo

    base_computable = trabajo.ingresos_brutos
    if not trabajo.opta_por_costos_y_gastos:
        base_computable += trabajo.ingresos_sin_vinculo_laboral

    if base_computable <= CERO:
        return CERO, "Sin rentas de trabajo computables: exención del 25 % no aplica"

    subtotal = _no_negativo(
        base_computable - trabajo.total_incrngo - otras_restas_de_trabajo
    )
    porcentual = subtotal * (limite.porcentaje or CERO)
    tope = (limite.tope_uvt or CERO) * parametros.uvt
    exenta = min(porcentual, tope)

    formula = (
        f"25% × ${subtotal.quantize(_CENTAVO)} (pagos laborales depurados) = "
        f"${porcentual.quantize(_CENTAVO)}, topado en "
        f"{limite.tope_uvt} UVT = ${tope.quantize(_CENTAVO)}"
    )
    if trabajo.opta_por_costos_y_gastos and trabajo.ingresos_sin_vinculo_laboral > CERO:
        formula += (
            "; se excluyen los honorarios sin vínculo laboral porque se optó por "
            "restar costos y gastos (art. 336 num. 4)"
        )
    return redondear_pesos(exenta), formula


def _aplicar_topes_propios(
    conceptos: List[ConceptoDepuracion],
    parametros: ParametrosAnuales,
    ingresos_base: Decimal,
) -> Tuple[List[ConceptoDepuracion], List[Renglon], List[str]]:
    """Recorta cada concepto a su propio tope, antes del límite general.

    El orden es el de la ley y no es intercambiable: primero el techo propio de
    cada concepto (1.200 UVT los intereses de vivienda, 16 UVT mensuales la
    medicina prepagada, 3.800 UVT los aportes previsionales), y solo después la
    suma pasa por el 40 % / 1.340 UVT del art. 336 num. 3.

    Al revés, una deducción improcedente entra a la bolsa y el límite general
    la tapa: el total parece razonable, la composición está mal y, si el límite
    general no alcanza a morder, el impuesto sale más bajo de lo que debe.

    Los conceptos que comparten tope —los aportes voluntarios a pensión y el
    ahorro en AFC comparten 3.800 UVT entre los dos— se recortan como grupo y
    a prorrata, no uno por uno.
    """
    ajustados: List[ConceptoDepuracion] = []
    renglones: List[Renglon] = []
    diagnosticos: List[str] = []

    def tope_en_pesos(tope) -> Optional[Decimal]:
        if tope.tope_uvt is None:
            return None
        meses = Decimal(12) if tope.es_mensual else Decimal(1)
        absoluto = tope.tope_uvt * parametros.uvt * meses
        if tope.porcentaje_de_ingresos is not None:
            return min(absoluto, ingresos_base * tope.porcentaje_de_ingresos)
        return absoluto

    # Conceptos agrupados por tope compartido; None = tope individual.
    grupos: dict = {}
    for concepto in conceptos:
        tope = parametros.topes_deducciones.get(concepto.codigo_tope or "")
        clave = tope.grupo if tope and tope.grupo else None
        grupos.setdefault(clave, []).append((concepto, tope))

    for clave, miembros in grupos.items():
        if clave is None:
            for concepto, tope in miembros:
                limite = tope_en_pesos(tope) if tope else None
                if limite is None or concepto.valor <= limite:
                    ajustados.append(concepto)
                    continue
                recorte = concepto.valor - limite
                ajustados.append(
                    ConceptoDepuracion(
                        nombre=concepto.nombre,
                        valor=redondear_pesos(limite),
                        sujeto_a_limite_general=concepto.sujeto_a_limite_general,
                        fuente_legal=concepto.fuente_legal,
                        codigo_tope=concepto.codigo_tope,
                    )
                )
                renglones.append(
                    Renglon(
                        f"CG-TOPE-{_slug(concepto.nombre)}",
                        f"{concepto.nombre} — recortado a su tope propio",
                        redondear_pesos(limite),
                        f"solicitado ${concepto.valor.quantize(_CENTAVO)}, tope "
                        f"${limite.quantize(_CENTAVO)}",
                        tope.fuente_legal,
                    )
                )
                diagnosticos.append(
                    f"«{concepto.nombre}»: se solicitaron "
                    f"${concepto.valor.quantize(_CENTAVO)} y el tope propio del "
                    f"concepto es ${limite.quantize(_CENTAVO)} "
                    f"({tope.fuente_legal}). Se recortaron "
                    f"${recorte.quantize(_CENTAVO)} antes de aplicar el límite "
                    f"general del art. 336."
                )
            continue

        # Tope compartido: se evalúa sobre la suma del grupo.
        tope = miembros[0][1]
        limite = tope_en_pesos(tope)
        solicitado = sum((c.valor for c, _ in miembros), CERO)
        if limite is None or solicitado <= limite:
            ajustados.extend(c for c, _ in miembros)
            continue

        factor = limite / solicitado
        for concepto, _ in miembros:
            ajustados.append(
                ConceptoDepuracion(
                    nombre=concepto.nombre,
                    valor=redondear_pesos(concepto.valor * factor),
                    sujeto_a_limite_general=concepto.sujeto_a_limite_general,
                    fuente_legal=concepto.fuente_legal,
                    codigo_tope=concepto.codigo_tope,
                )
            )
        renglones.append(
            Renglon(
                f"CG-TOPE-GRUPO-{_slug(clave)}",
                f"Tope compartido — {clave.replace('_', ' ').lower()}",
                redondear_pesos(limite),
                f"solicitado entre {len(miembros)} concepto(s) "
                f"${solicitado.quantize(_CENTAVO)}, tope conjunto "
                f"${limite.quantize(_CENTAVO)}, repartido a prorrata",
                tope.fuente_legal,
            )
        )
        diagnosticos.append(
            f"Los conceptos que comparten el tope de "
            f"{clave.replace('_', ' ').lower()} suman "
            f"${solicitado.quantize(_CENTAVO)} y ese tope es "
            f"${limite.quantize(_CENTAVO)} ({tope.fuente_legal}). No es un tope "
            f"por concepto: se recortaron ${(solicitado - limite).quantize(_CENTAVO)} "
            f"repartidos a prorrata."
        )

    return ajustados, renglones, diagnosticos


def _aplicar_limite_general(
    solicitado: Decimal,
    base_del_porcentaje: Decimal,
    parametros: ParametrosAnuales,
) -> Tuple[Decimal, str, List[str]]:
    """Aplica el límite del art. 336 num. 3: 40 % con tope de 1.340 UVT.

    La base del porcentaje son los ingresos de la cédula general menos los
    ingresos no constitutivos de renta, antes de restar costos y gastos. El
    resultado es el menor de tres cifras: lo solicitado, el 40 % de esa base y
    el tope absoluto en UVT.
    """
    limite = parametros.limite_general
    porcentual = base_del_porcentaje * (limite.porcentaje or CERO)
    tope = (limite.tope_uvt or CERO) * parametros.uvt
    aceptado = min(solicitado, porcentual, tope)

    diagnosticos: List[str] = []
    if aceptado < solicitado:
        recorte = solicitado - aceptado
        cual = "el 40 % de los ingresos depurados" if porcentual <= tope else f"el tope de {limite.tope_uvt} UVT"
        diagnosticos.append(
            f"El límite del art. 336 num. 3 recortó ${recorte.quantize(_CENTAVO)} "
            f"de las rentas exentas y deducciones solicitadas: se aceptaron "
            f"${aceptado.quantize(_CENTAVO)} de ${solicitado.quantize(_CENTAVO)} "
            f"porque {cual} es la cifra menor. El exceso no se traslada a otros "
            f"años ni a otras cédulas."
        )

    formula = (
        f"menor entre: solicitado ${solicitado.quantize(_CENTAVO)}, "
        f"40% × ${base_del_porcentaje.quantize(_CENTAVO)} = ${porcentual.quantize(_CENTAVO)}, "
        f"y {limite.tope_uvt} UVT = ${tope.quantize(_CENTAVO)}"
    )
    return redondear_pesos(aceptado), formula, diagnosticos


def _deducciones_fuera_del_limite(
    insumos: InsumosLiquidacion, parametros: ParametrosAnuales
) -> Tuple[dict, List[Renglon]]:
    """Deducciones que la ley dejó por fuera del límite del 40 %.

    Son dos: la deducción por dependientes (72 UVT por cada uno, hasta cuatro,
    adicional al límite general) y el 1 % de las compras soportadas en factura
    electrónica, topado en 240 UVT (art. 336 num. 5).

    Se devuelven separadas y no sumadas porque el formulario 210 las pide en
    casillas distintas —139 y 28— y cada una tiene además su propio techo: la
    de dependientes no puede exceder la renta líquida ordinaria de las rentas
    de trabajo, y la del 1 % no puede dar lugar a pérdidas.
    """
    renglones: List[Renglon] = []
    montos: dict = {}

    dependientes = max(0, min(insumos.numero_dependientes, parametros.max_dependientes))
    if dependientes:
        valor = redondear_pesos(
            Decimal(dependientes) * (parametros.deduccion_dependientes.tope_uvt or CERO) * parametros.uvt
        )
        montos["DEPENDIENTES_336"] = valor
        renglones.append(
            Renglon(
                codigo="DED-DEPENDIENTES",
                nombre="Deducción por dependientes",
                valor=valor,
                formula=(
                    f"{dependientes} dependiente(s) × "
                    f"{parametros.deduccion_dependientes.tope_uvt} UVT × ${parametros.uvt}"
                ),
                fuente_legal=parametros.deduccion_dependientes.fuente_legal,
            )
        )
        if insumos.numero_dependientes > parametros.max_dependientes:
            renglones[-1].formula += (
                f" (se informaron {insumos.numero_dependientes}; la ley reconoce "
                f"máximo {parametros.max_dependientes})"
            )

    if insumos.compras_con_factura_electronica > CERO:
        limite = parametros.deduccion_compras
        porcentual = insumos.compras_con_factura_electronica * (limite.porcentaje or CERO)
        tope = (limite.tope_uvt or CERO) * parametros.uvt
        valor = redondear_pesos(min(porcentual, tope))
        montos["COMPRAS_1_PCT"] = valor
        renglones.append(
            Renglon(
                codigo="DED-COMPRAS-1PCT",
                nombre="Deducción del 1 % de compras con factura electrónica",
                valor=valor,
                formula=(
                    f"menor entre 1% × ${insumos.compras_con_factura_electronica.quantize(_CENTAVO)} "
                    f"= ${porcentual.quantize(_CENTAVO)} y {limite.tope_uvt} UVT = "
                    f"${tope.quantize(_CENTAVO)}. Requiere pago por medio electrónico y "
                    f"factura electrónica de venta con validación previa"
                ),
                fuente_legal=limite.fuente_legal,
            )
        )

    return montos, renglones


# ---------------------------------------------------------------------------
# Liquidación completa
# ---------------------------------------------------------------------------


def liquidar(
    insumos: InsumosLiquidacion, parametros: ParametrosAnuales
) -> Liquidacion:
    """Liquida el impuesto de renta y complementarios de una persona natural residente.

    El orden de los pasos es el del Estatuto, no uno conveniente: cédula general
    depurada con su límite, cédula de pensiones, dividendos, tabla del art. 241,
    ganancias ocasionales con tarifa propia, descuentos, anticipo y saldo. Cada
    paso deja su renglón con la fórmula y la norma.
    """
    if insumos.anio_gravable != parametros.anio_gravable:
        raise AnioGravableNoSoportadoError(
            f"Los parámetros recibidos son del año {parametros.anio_gravable} "
            f"y los insumos del {insumos.anio_gravable}"
        )

    uvt = parametros.uvt
    liq = Liquidacion(
        anio_gravable=insumos.anio_gravable,
        uvt=uvt,
        regimen=parametros.regimen,
        notas=list(parametros.notas),
    )
    R = liq.renglones.append

    # --- Patrimonio -------------------------------------------------------
    R(Renglon("PAT-BRUTO", "Total patrimonio bruto", insumos.patrimonio.patrimonio_bruto,
              "Suma de los activos poseídos a 31 de diciembre", "Arts. 261 y 267 ET",
              casilla=29))
    R(Renglon("PAT-DEUDAS", "Deudas", insumos.patrimonio.deudas,
              "Pasivos vigentes a 31 de diciembre", "Art. 283 ET", casilla=30))
    R(Renglon("PAT-LIQUIDO", "Total patrimonio líquido",
              insumos.patrimonio.patrimonio_liquido,
              "Patrimonio bruto − deudas", "Art. 282 ET", casilla=31))

    # --- Depreciación (arts. 128 a 131 y 137 ET) --------------------------
    # Se trabaja sobre copias: más abajo se les suma la depreciación y se les
    # descuentan los costos no procedentes, y liquidar dos veces los mismos
    # insumos —como hace el simulador de escenarios— no puede dar resultados
    # distintos la segunda vez.
    trabajo = insumos.trabajo
    capital = replace(insumos.capital)
    no_laborales = replace(insumos.no_laborales)

    depreciacion = calcular_depreciacion(insumos.activos_depreciables, parametros)
    liq.diagnosticos.extend(depreciacion.diagnosticos)
    for descripcion, valor, formula in depreciacion.detalle:
        R(Renglon(f"DEP-{_slug(descripcion)}", f"Depreciación — {descripcion}", valor,
                  formula, parametros.fuente_depreciacion))
    if depreciacion.total > CERO:
        R(Renglon("DEP-TOTAL", "Depreciación deducible del periodo", depreciacion.total,
                  f"Suma de la depreciación de {len(depreciacion.detalle)} activo(s), "
                  f"imputada a {insumos.cedula_depreciacion}",
                  parametros.fuente_depreciacion))
        destino = capital if insumos.cedula_depreciacion == "CAPITAL" else no_laborales
        destino.depreciacion += depreciacion.total

    # --- Cédula general ----------------------------------------------------
    #
    # El formulario 210 no pide la cédula general como un total: la pide como
    # una grilla de diecisiete filas por cuatro columnas, con una casilla en
    # cada celda. El módulo `cedula_general` arma esa grilla y aplica el límite
    # del art. 336 num. 3, que es uno solo para toda la cédula y se reparte
    # entre las columnas en cascada, en el orden que fija el instructivo.
    costos_cg = capital.total_costos + no_laborales.total_costos
    if trabajo.opta_por_costos_y_gastos:
        costos_cg += trabajo.costos_y_gastos_sin_vinculo_laboral

    # --- Bancarización (art. 771-5 ET) ------------------------------------
    #
    # El efectivo rechazado no es un costo procedente, así que se descuenta de
    # los costos de la columna que lo originó en vez de sumarse de vuelta a la
    # renta líquida: así la casilla de costos del formulario queda con la cifra
    # que de verdad se declara. Se reparte a prorrata de los costos de cada
    # columna porque el art. 771-5 fija un límite global y no identifica a qué
    # subcédula pertenece cada pago.
    banca = calcular_bancarizacion(insumos.bancarizacion, costos_cg, parametros)
    liq.diagnosticos.extend(banca.diagnosticos)
    if banca.aplica:
        R(Renglon("CG-EFECTIVO-ACEPTADO", "Pagos en efectivo aceptados",
                  banca.efectivo_aceptado, banca.formula,
                  parametros.bancarizacion.fuente_legal))
        if banca.efectivo_rechazado > CERO:
            R(Renglon("CG-EFECTIVO-RECHAZADO",
                      "Pagos en efectivo no deducibles (excluidos de los costos)",
                      banca.efectivo_rechazado,
                      "Exceso sobre el límite del art. 771-5: se excluye de los costos "
                      "procedentes de cada subcédula a prorrata, porque no es un costo "
                      "aceptado fiscalmente",
                      parametros.bancarizacion.fuente_legal))
            if costos_cg > CERO:
                rechazado_restante = banca.efectivo_rechazado
                destinos = [
                    (capital, capital.total_costos),
                    (no_laborales, no_laborales.total_costos),
                ]
                con_costos = [(d, c) for d, c in destinos if c > CERO]
                for indice, (destino, costos_destino) in enumerate(con_costos):
                    if indice == len(con_costos) - 1:
                        # La última absorbe el redondeo para que las partes
                        # sumen exactamente el rechazo y no se pierda un peso.
                        parte = rechazado_restante
                    else:
                        parte = (
                            banca.efectivo_rechazado * costos_destino / costos_cg
                        ).quantize(_CENTAVO)
                        rechazado_restante -= parte
                    destino.costos_no_procedentes += parte
                costos_cg = _no_negativo(costos_cg - banca.efectivo_rechazado)

    # --- Topes propios de cada concepto, antes del límite general ---------
    base_limite = _no_negativo(
        trabajo.total_ingresos
        + capital.ingresos_brutos
        + no_laborales.ingresos_brutos
        - trabajo.total_incrngo
        - capital.ingresos_no_constitutivos
        - no_laborales.ingresos_no_constitutivos
    )
    conceptos, renglones_tope, diag_tope = _aplicar_topes_propios(
        insumos.conceptos_depuracion, parametros, base_limite
    )
    for renglon in renglones_tope:
        R(renglon)
    liq.diagnosticos.extend(diag_tope)

    suma_limitables = sum(
        (c.valor for c in conceptos if c.sujeto_a_limite_general), CERO
    )
    exenta_trabajo, formula_exenta = _renta_exenta_trabajo(
        insumos, parametros, suma_limitables
    )
    if exenta_trabajo > CERO:
        R(Renglon("CG-EXENTA-25", "Renta exenta del 25 % de rentas de trabajo",
                  exenta_trabajo, formula_exenta,
                  parametros.renta_exenta_trabajo.fuente_legal))

    # --- Deducciones que la ley dejó fuera del límite del num. 3 ----------
    fuera_calculadas, renglones_fuera = _deducciones_fuera_del_limite(insumos, parametros)
    for renglon in renglones_fuera:
        R(renglon)
    dependientes_336 = fuera_calculadas.get("DEPENDIENTES_336", CERO)
    compras_1_pct = fuera_calculadas.get("COMPRAS_1_PCT", CERO)

    # --- La grilla ---------------------------------------------------------
    cg = depurar_cedula_general(
        trabajo,
        capital,
        no_laborales,
        conceptos,
        exenta_trabajo,
        dependientes_336,
        compras_1_pct,
        CERO,
        parametros,
    )

    # --- Compensación de pérdidas de años anteriores ----------------------
    #
    # Va después del límite y no antes: el formulario compensa contra la renta
    # líquida ordinaria del ejercicio (casillas 87, 70, 54), que ya tiene
    # restadas las rentas exentas y deducciones limitadas de la columna.
    renta_por_tipo = {
        "TRABAJO_SIN_VINCULO": cg.columnas[SIN_VINCULO].renta_liquida_ordinaria_ejercicio,
        "CAPITAL": cg.columnas[CAPITAL].renta_liquida_ordinaria_ejercicio,
        "NO_LABORAL": cg.columnas[NO_LABORAL].renta_liquida_ordinaria_ejercicio,
    }
    compensacion = calcular_compensacion_perdidas(
        insumos.perdidas_compensables, renta_por_tipo, insumos.anio_gravable, parametros
    )
    liq.diagnosticos.extend(compensacion.diagnosticos)
    for nombre, valor, formula in compensacion.detalle:
        R(Renglon(f"CG-PERD-{_slug(nombre)}", nombre, valor, formula,
                  parametros.fuente_compensacion_perdidas))
    cg.columnas[SIN_VINCULO].compensaciones = compensacion.por_tipo.get(
        "TRABAJO_SIN_VINCULO", CERO
    )
    cg.columnas[CAPITAL].compensaciones = compensacion.por_tipo.get("CAPITAL", CERO)
    cg.columnas[NO_LABORAL].compensaciones = compensacion.por_tipo.get("NO_LABORAL", CERO)

    liq.diagnosticos.extend(cg.diagnosticos)

    # --- Totales agregados de la cédula general ---------------------------
    #
    # Se derivan de la grilla, no se calculan aparte: son la vista resumida que
    # el contador lee primero y que usa el borrador en PDF. Calcularlos por
    # separado sería tener dos verdades que con el tiempo se separan.
    R(Renglon("CG-INGRESOS", "Ingresos brutos de la cédula general",
              sum((c.ingresos_brutos for c in cg.columnas.values()), CERO),
              "Casillas 32 + 43 + 58 + 74. No incluye dividendos ni ganancias "
              "ocasionales",
              "Arts. 335, 338 y 340 ET"))
    R(Renglon("CG-INCRNGO", "Ingresos no constitutivos de renta ni ganancia ocasional",
              sum((c.ingresos_no_constitutivos for c in cg.columnas.values()), CERO),
              "Casillas 33 + 44 + 59 + 76", "Arts. 55 y 56 ET"))
    devoluciones_cg = sum((c.devoluciones for c in cg.columnas.values()), CERO)
    if devoluciones_cg > CERO:
        R(Renglon("CG-DEVOLUCIONES", "Devoluciones, rebajas y descuentos",
                  devoluciones_cg,
                  "Casilla 75. Disminuyen los ingresos ordinarios del período",
                  "Art. 340 ET"))
    R(Renglon("CG-COSTOS", "Costos y gastos procedentes",
              sum((c.costos_y_deducciones for c in cg.columnas.values()), CERO),
              "Casillas 45 + 60 + 77. Incluye el costo de ventas del inventario y la "
              "depreciación, y los de honorarios sin vínculo laboral solo si se optó "
              "por ellos en vez de la renta exenta del art. 206 num. 10",
              "Art. 336 num. 4 ET"))
    if capital.costo_de_ventas + no_laborales.costo_de_ventas > CERO:
        R(Renglon("CG-COSTO-VENTAS", "Costo de ventas del inventario",
                  capital.costo_de_ventas + no_laborales.costo_de_ventas,
                  "Calculado por el kardex del módulo de inventario con el método de "
                  "costeo de cada producto",
                  "Arts. 62 y 66 ET"))
    R(Renglon("CG-RL-ANTES", "Renta líquida antes de rentas exentas y deducciones",
              sum((c.renta_liquida for c in cg.columnas.values()), CERO),
              "Casillas 34 + 46 + 61 + 78: suma de la renta líquida de cada subcédula",
              "Art. 336 ET"))
    for concepto in conceptos:
        prefijo = "CG-SOL" if concepto.sujeto_a_limite_general else "CG-NOLIM"
        nota = (
            "Solicitado por el contribuyente, sujeto al límite del art. 336 num. 3"
            if concepto.sujeto_a_limite_general
            else "No sujeto al límite del art. 336 num. 3"
        )
        R(Renglon(f"{prefijo}-{_slug(concepto.nombre)}", concepto.nombre,
                  concepto.valor, nota, concepto.fuente_legal))
    R(Renglon("CG-EXENTAS-LIMITADAS",
              "Rentas exentas y deducciones imputables (limitadas)",
              cg.limitadas_total,
              "Casillas 41 + 53 + 69 + 86: menor entre lo solicitado, el "
              f"{porcentaje(parametros.limite_general.porcentaje or CERO)} % de la base "
              f"y {parametros.limite_general.tope_uvt} UVT, más las rentas exentas que "
              "la ley dejó fuera del límite",
              parametros.limite_general.fuente_legal))
    total_compensado = sum((c.compensaciones for c in cg.columnas.values()), CERO)
    if total_compensado > CERO:
        R(Renglon("CG-COMPENSACION", "Compensación de pérdidas de años anteriores",
                  total_compensado,
                  "Casillas 56 + 72 + 89. Imputadas contra la renta líquida ordinaria "
                  "del ejercicio del mismo tipo de renta; las rentas de trabajo con "
                  "vínculo laboral no admiten compensación",
                  parametros.fuente_compensacion_perdidas))

    # --- Los renglones de la grilla, cada uno con su casilla --------------
    R(Renglon("CG-BASE-LIMITE", "Base para el límite del 40 %", cg.base_del_limite,
              "Ingresos brutos de las cuatro subcédulas − ingresos no constitutivos. "
              "Las devoluciones de la casilla 75 no se restan de esta base",
              parametros.limite_general.fuente_legal))
    for numero, nombre_fila, valor in casillas_de(cg):
        R(Renglon(f"CG-C{numero}", f"[{numero}] {nombre_fila}", valor,
                  f"Casilla {numero} del formulario 210",
                  "Arts. 335, 336, 338 y 340 ET", casilla=numero))

    # Las pérdidas del ejercicio no desaparecen al truncar en cero: el art. 147
    # permite compensarlas en los años siguientes y el contador tiene que
    # registrarlas para poder hacerlo.
    for subcedula in SUBCEDULAS:
        perdida = cg.columnas[subcedula].perdida_liquida
        if perdida > CERO:
            R(Renglon(f"CG-PERDIDA-EJERCICIO-{subcedula}",
                      f"Pérdida del ejercicio — {_NOMBRE_SUBCEDULA[subcedula]}",
                      perdida,
                      "Los costos y deducciones de esta subcédula superaron sus "
                      "ingresos. La renta líquida se trunca en cero y el exceso queda "
                      "como pérdida compensable",
                      "Arts. 147 y 330 ET"))
            liq.diagnosticos.append(
                f"Los costos imputados a {_NOMBRE_SUBCEDULA[subcedula]} superan sus "
                f"ingresos en ${perdida.quantize(_CENTAVO)}: esa parte NO se dedujo "
                f"este año. Regístrela como pérdida fiscal de {insumos.anio_gravable} "
                f"para poder compensarla en los próximos "
                f"{parametros.anios_compensacion_perdidas} años, o revise si la "
                f"depreciación y los costos están imputados a la subcédula correcta."
            )

    if cg.deduccion_dependientes > CERO:
        R(Renglon("CG-C139", "[139] Adición por dependientes a la casilla 92",
                  cg.deduccion_dependientes,
                  "72 UVT por dependiente, hasta cuatro, sin exceder la renta líquida "
                  "ordinaria de las rentas de trabajo (casillas 42 y 57)",
                  "Art. 336 num. 3 ET", casilla=139))
    if cg.deduccion_compras > CERO:
        R(Renglon("CG-C28", "[28] Uno por ciento (1 %) de compras con factura electrónica",
                  cg.deduccion_compras,
                  "1 % de las compras soportadas en factura electrónica, hasta 240 UVT, "
                  "sin que pueda dar lugar a pérdidas",
                  "Art. 336 num. 5 ET", casilla=28))

    # --- Casilla 140: tope indicativo del art. 336-1 ET --------------------
    #
    # El instructivo pide marcarla cuando los costos y deducciones de las
    # rentas de trabajo sin vínculo laboral (casilla 45) superan el 60 % de sus
    # ingresos brutos (casilla 43). No cambia el impuesto: es un aviso a la
    # DIAN, y a quien la marca le conviene tener los soportes a la mano.
    sin_vinculo = cg.columnas[SIN_VINCULO]
    if (
        sin_vinculo.ingresos_brutos > CERO
        and sin_vinculo.costos_y_deducciones
        > sin_vinculo.ingresos_brutos * Decimal("0.60")
    ):
        liq.casillas_marcadas.append(140)
        liq.diagnosticos.append(
            f"Los costos de las rentas de trabajo sin vínculo laboral "
            f"(${sin_vinculo.costos_y_deducciones.quantize(_CENTAVO)}) superan el 60 % "
            f"de sus ingresos (${sin_vinculo.ingresos_brutos.quantize(_CENTAVO)}): hay "
            f"que marcar la casilla 140 del formulario (tope indicativo del art. "
            f"336-1 ET). No cambia el impuesto, pero la DIAN puede pedir los "
            f"soportes de esos costos."
        )

    R(Renglon("CG-C91", "[91] Renta líquida cédula general", cg.casilla_91,
              "Casillas 41 + 42 + 53 + 57 + 69 + 73 + 86 + 90",
              "Art. 336 ET", casilla=91))
    R(Renglon("CG-C92", "[92] Rentas exentas y deducciones imputables limitadas",
              cg.casilla_92,
              "Casillas 28 + 41 + 53 + 69 + 86 + 139",
              parametros.limite_general.fuente_legal, casilla=92))
    R(Renglon("CG-C93", "[93] Renta líquida ordinaria cédula general", cg.casilla_93,
              "Casilla 91 − casilla 92", "Art. 336 ET", casilla=93))

    # Alias estable del total de la cédula general. El resto del motor y las
    # pruebas lo consultan por este código; la casilla 97 lo vuelve a emitir
    # más abajo, una vez conocidas las rentas gravables por comparación
    # patrimonial.
    renta_liquida_cg = cg.casilla_93
    R(Renglon("CG-RENTA-LIQUIDA", "Renta líquida gravable de la cédula general",
              renta_liquida_cg,
              "Casilla 93: renta líquida de la cédula general menos las rentas "
              "exentas y deducciones imputables limitadas",
              "Art. 336 ET"))

    # --- Cédula de pensiones ----------------------------------------------
    pensiones = insumos.pensiones
    base_pensiones = _no_negativo(
        pensiones.ingresos_brutos - pensiones.ingresos_no_constitutivos
    )
    meses = max(0, min(pensiones.meses_causados, 12))
    tope_pensiones = (
        parametros.renta_exenta_pensiones_uvt_mensual * Decimal(meses) * uvt
    )
    exenta_pensiones = min(base_pensiones, tope_pensiones)
    renta_liquida_pensiones = _no_negativo(base_pensiones - exenta_pensiones)
    if pensiones.ingresos_brutos > CERO:
        R(Renglon("PEN-INGRESOS", "Ingresos por pensiones", pensiones.ingresos_brutos,
                  "Mesadas y demás pagos pensionales del año", "Art. 337 ET",
                  casilla=99))
        if pensiones.ingresos_no_constitutivos > CERO:
            R(Renglon("PEN-INCRNGO", "Ingresos no constitutivos de renta de pensiones",
                      pensiones.ingresos_no_constitutivos,
                      "Aportes obligatorios a salud sobre las mesadas",
                      "Art. 56 ET", casilla=100))
        R(Renglon("PEN-BASE", "Renta líquida de la cédula de pensiones", base_pensiones,
                  "Casilla 99 − casilla 100", "Art. 337 ET", casilla=101))
        R(Renglon("PEN-EXENTA", "Renta exenta de pensiones", exenta_pensiones,
                  f"Topada en {parametros.renta_exenta_pensiones_uvt_mensual} UVT × "
                  f"{meses} mes(es) = ${tope_pensiones.quantize(_CENTAVO)}",
                  parametros.fuente_renta_exenta_pensiones, casilla=102))
        R(Renglon("PEN-RENTA-LIQUIDA", "Renta líquida gravable de pensiones",
                  renta_liquida_pensiones, "Ingresos − no constitutivos − renta exenta",
                  "Art. 337 ET", casilla=103))

    # --- Dividendos --------------------------------------------------------
    div = insumos.dividendos
    tarifa_240 = (
        div.tarifa_gravados
        if div.tarifa_gravados is not None
        else parametros.tarifa_dividendos_gravados
    )
    impuesto_dividendos_gravados = redondear_pesos(div.gravados * tarifa_240)
    # Lo que entra a la tabla del art. 241: los no gravados completos y los
    # gravados una vez restado su propio impuesto (casilla 111 = … + 107 + 108
    # − 118). Llevarlos completos gravaría dos veces la parte que ya pagó el 35 %.
    renta_liquida_dividendos = (
        div.no_gravados + div.gravados - impuesto_dividendos_gravados
    )
    if div.no_gravados > CERO:
        R(Renglon("DIV-NO-GRAVADOS", "Dividendos — 1a subcédula (no gravados)",
                  div.no_gravados,
                  "Dividendos distribuidos como no gravados según el certificado de "
                  "la sociedad", "Art. 49 num. 3 ET", casilla=107))
    if div.gravados > CERO:
        R(Renglon("DIV-GRAVADOS", "Dividendos — 2a subcédula (gravados)",
                  div.gravados,
                  "Dividendos distribuidos como gravados según el certificado de la "
                  "sociedad", "Art. 49 par. 2 ET", casilla=108))
        R(Renglon("DIV-IMPUESTO-GRAVADOS",
                  "Impuesto por dividendos gravados, 2a subcédula",
                  impuesto_dividendos_gravados,
                  f"{porcentaje(tarifa_240)}% × ${div.gravados.quantize(_CENTAVO)}. "
                  "Se resta de la base de la tabla del art. 241 y se suma al "
                  "impuesto en la casilla 121",
                  parametros.fuente_dividendos_gravados, casilla=118))
        if div.tarifa_gravados is None:
            liq.notas.append(
                f"A los dividendos gravados se les aplicó la tarifa general del art. "
                f"240 ({porcentaje(tarifa_240)}%). Si el certificado de la sociedad "
                f"indica una tarifa diferencial, hay que usar esa."
            )
    if renta_liquida_dividendos > CERO:
        R(Renglon("DIV-RENTA-LIQUIDA", "Renta líquida cedular de dividendos y participaciones",
                  renta_liquida_dividendos,
                  "Dividendos no gravados + gravados − impuesto del art. 240 sobre los "
                  "gravados (casillas 107 + 108 − 118). Es lo que entra a la tabla "
                  "del art. 241",
                  "Arts. 242 y 331 ET, modificados por la Ley 2277 de 2022"))

    # --- Ganancias ocasionales --------------------------------------------
    #
    # Se calculan antes de la base ordinaria porque la comparación patrimonial
    # necesita la ganancia ocasional neta para saber qué parte del incremento
    # del patrimonio está explicada.
    go = insumos.ganancias_ocasionales
    base_go = _no_negativo(go.ingresos - go.costos - go.ganancia_exenta)
    impuesto_go = redondear_pesos(base_go * parametros.tarifa_ganancia_ocasional)
    impuesto_loterias = redondear_pesos(
        go.loterias_rifas_apuestas * parametros.tarifa_ganancia_ocasional_loterias
    )
    if go.ingresos > CERO or go.loterias_rifas_apuestas > CERO:
        R(Renglon("GO-INGRESOS", "Ingresos por ganancias ocasionales",
                  go.ingresos + go.loterias_rifas_apuestas,
                  "Incluye loterías, rifas y apuestas", "Arts. 299 a 306 ET",
                  casilla=112))
        if go.costos > CERO:
            R(Renglon("GO-COSTOS", "Costos por ganancias ocasionales", go.costos,
                      "Costo fiscal de los bienes enajenados", "Art. 300 ET",
                      casilla=113))
        if go.ganancia_exenta > CERO:
            R(Renglon("GO-EXENTA", "Ganancias ocasionales no gravadas y exentas",
                      go.ganancia_exenta, "Parte exenta según la norma aplicable",
                      "Arts. 307 a 311-1 ET", casilla=114))
        R(Renglon("GO-GRAVABLE", "Ganancias ocasionales gravables",
                  base_go + go.loterias_rifas_apuestas,
                  "Casilla 112 − casilla 113 − casilla 114", "Art. 311 ET",
                  casilla=115))
        R(Renglon("GO-BASE", "Ganancia ocasional gravable", base_go,
                  "Ingresos por ganancia ocasional − costos − ganancia exenta",
                  "Arts. 299 a 311-1 ET"))
        R(Renglon("GO-IMPUESTO", "Impuesto de ganancias ocasionales",
                  impuesto_go + impuesto_loterias,
                  f"{porcentaje(parametros.tarifa_ganancia_ocasional)}% × "
                  f"${base_go.quantize(_CENTAVO)}"
                  + (f" + {porcentaje(parametros.tarifa_ganancia_ocasional_loterias)}% × "
                     f"${go.loterias_rifas_apuestas.quantize(_CENTAVO)} (loterías, rifas y apuestas)"
                     if go.loterias_rifas_apuestas > CERO else ""),
                  parametros.fuente_ganancia_ocasional, casilla=127))

    # --- Base gravable y tabla del art. 241 --------------------------------
    base_ordinaria = renta_liquida_cg + renta_liquida_pensiones + renta_liquida_dividendos

    # --- Renta por comparación patrimonial (arts. 236 a 239 ET) -----------
    comparacion = calcular_comparacion_patrimonial(
        insumos.comparacion_patrimonial,
        insumos.patrimonio.patrimonio_liquido,
        base_ordinaria,
        cg.limitadas_total + exenta_pensiones,
        base_go,
    )
    liq.diagnosticos.extend(comparacion.diagnosticos)
    renta_comparacion = CERO
    if comparacion.aplica and comparacion.diferencia > CERO:
        R(Renglon("COMP-PATRIMONIAL", "Diferencia patrimonial no justificada",
                  comparacion.diferencia, comparacion.formula,
                  "Arts. 236 a 239 ET; art. 1.2.1.19.2 del DUR 1625 de 2016"))
        if insumos.comparacion_patrimonial.aceptar_como_renta_gravable:
            renta_comparacion = comparacion.diferencia
            R(Renglon("COMP-PATRIMONIAL-GRAVADA",
                      "Renta gravable por comparación patrimonial", renta_comparacion,
                      "Incorporada a la base por decisión del contador: el art. 236 "
                      "admite prueba en contrario y no se incorpora sola",
                      "Art. 236 ET", casilla=96))
    R(Renglon("CG-C97", "[97] Renta líquida gravable de la cédula general",
              renta_liquida_cg + renta_comparacion,
              "Casilla 93 + casilla 96 − casillas 94 y 95 (que este borrador no "
              "maneja: pérdidas de 2018 y anteriores y excesos de renta presuntiva)",
              "Art. 336 ET", casilla=97))

    presuntiva = insumos.renta_presuntiva
    # La presuntiva se compara solo contra la cédula general (casillas 97 y
    # 98); pensiones y dividendos se suman después, gane quien gane: casilla
    # 111 = mayor(97, 98) + 103 + 107 + 108 − 118.
    casilla_97 = renta_liquida_cg + renta_comparacion
    por_presuntiva = presuntiva > casilla_97
    base_241 = (
        max(casilla_97, presuntiva)
        + renta_liquida_pensiones
        + renta_liquida_dividendos
    )
    if presuntiva > CERO:
        R(Renglon("RENTA-PRESUNTIVA", "Renta presuntiva", presuntiva,
                  f"Tarifa vigente: {porcentaje(parametros.tarifa_renta_presuntiva)}%",
                  parametros.fuente_renta_presuntiva, casilla=98))
        if por_presuntiva:
            liq.diagnosticos.append(
                f"La renta presuntiva (${presuntiva.quantize(_CENTAVO)}) superó la renta "
                f"líquida gravable de la cédula general "
                f"(${casilla_97.quantize(_CENTAVO)}) y la reemplazó en la base del "
                f"impuesto; las rentas de pensiones y de dividendos se suman igual."
            )

    R(Renglon("BASE-GRAVABLE", "Renta líquida gravable total", base_241,
              "Mayor entre la renta líquida gravable de la cédula general (casilla "
              "97) y la renta presuntiva (98), más pensiones (103) y dividendos "
              "(107 + 108 − 118)",
              "Arts. 241, 331 y 188 ET", casilla=111))

    impuesto_renta, formula_impuesto, _ = aplicar_tabla(base_241, parametros.tabla_renta, uvt)
    R(Renglon("IMP-RENTA", "Impuesto sobre la renta líquida gravable", impuesto_renta,
              formula_impuesto, parametros.fuente_tabla_renta,
              casilla=117 if por_presuntiva else 116))
    # Desde aquí «impuesto de renta» es el total de la casilla 121: el de la
    # tabla más el del art. 240 sobre los dividendos gravados.
    impuesto_renta = impuesto_renta + impuesto_dividendos_gravados
    R(Renglon("IMP-TOTAL-RENTA", "Total impuesto sobre las rentas líquidas gravables",
              impuesto_renta, "Casillas 116 + 117 + 118 + 119 + 120",
              parametros.fuente_tabla_renta, casilla=121))

    total_a_cargo = impuesto_renta + impuesto_go + impuesto_loterias
    R(Renglon("TOTAL-A-CARGO", "Total impuesto a cargo", total_a_cargo,
              "Impuesto sobre la renta + impuesto de ganancias ocasionales",
              "Art. 241 y arts. 313 y siguientes ET"))

    # --- Descuentos tributarios --------------------------------------------
    umbral_descuento = (parametros.descuento_dividendos.tope_uvt or CERO) * uvt
    exceso_dividendos = _no_negativo(renta_liquida_dividendos - umbral_descuento)
    descuento_dividendos = redondear_pesos(
        exceso_dividendos * (parametros.descuento_dividendos.porcentaje or CERO)
    )
    if descuento_dividendos > CERO:
        R(Renglon("DESC-DIVIDENDOS", "Descuento tributario por dividendos",
                  descuento_dividendos,
                  f"{porcentaje(parametros.descuento_dividendos.porcentaje)}% × "
                  f"el exceso de la renta líquida cedular de dividendos sobre "
                  f"{parametros.descuento_dividendos.tope_uvt} UVT "
                  f"(${umbral_descuento.quantize(_CENTAVO)})",
                  parametros.descuento_dividendos.fuente_legal, casilla=124))

    # El techo es el impuesto de renta, no la suma con el de ganancias
    # ocasionales: en el formulario la casilla 126 es 121 − 125, y el impuesto
    # de ganancias ocasionales entra después, en la 127, sin descuentos.
    descuentos_solicitados = descuento_dividendos + insumos.otros_descuentos_tributarios
    descuentos = min(descuentos_solicitados, impuesto_renta)
    if descuentos < descuentos_solicitados:
        liq.diagnosticos.append(
            f"Los descuentos tributarios se recortaron a ${descuentos.quantize(_CENTAVO)}: "
            f"no pueden exceder el impuesto sobre la renta y el excedente de "
            f"${(descuentos_solicitados - descuentos).quantize(_CENTAVO)} se pierde."
        )
    R(Renglon("TOTAL-DESCUENTOS", "Total descuentos tributarios", descuentos,
              "Limitados al impuesto sobre la renta", "Arts. 254-1 y 259 ET",
              casilla=125))
    R(Renglon("IMP-NETO-RENTA", "Impuesto neto de renta (sin ganancias ocasionales)",
              impuesto_renta - descuentos, "Casilla 121 − casilla 125", "Art. 259 ET",
              casilla=126))

    impuesto_neto = _no_negativo(total_a_cargo - descuentos)
    R(Renglon("IMP-NETO", "Impuesto neto de renta", impuesto_neto,
              "Total impuesto a cargo − descuentos tributarios. Es la casilla 129 "
              "del formulario: 126 + 127", "Art. 259 ET", casilla=129))

    # --- Retenciones y anticipos -------------------------------------------
    retenciones = (
        insumos.retenciones_en_la_fuente + div.retencion_practicada + go.retenciones
    )
    R(Renglon("RETENCIONES", "Total retenciones en la fuente", retenciones,
              "Retenciones del año, incluidas las de dividendos y ganancias ocasionales",
              "Art. 373 ET", casilla=132))
    if insumos.anticipo_pagado_anio_anterior > CERO:
        R(Renglon("ANTICIPO-ANTERIOR", "Anticipo liquidado el año gravable anterior",
                  insumos.anticipo_pagado_anio_anterior,
                  "Casilla de anticipo de la declaración del año anterior",
                  "Art. 807 ET", casilla=130))
    if insumos.saldo_a_favor_anio_anterior > CERO:
        R(Renglon("SALDO-FAVOR-ANTERIOR", "Saldo a favor del año gravable anterior",
                  insumos.saldo_a_favor_anio_anterior,
                  "Sin solicitud de devolución ni compensación", "Art. 815 ET",
                  casilla=131))

    # --- Anticipo del año siguiente (art. 807 ET) -------------------------
    #
    # La norma permite dos procedimientos y el contribuyente escoge libremente,
    # pudiendo cambiar de año en año. Casi siempre conviene el menor, así que
    # el motor calcula los dos y deja elegir —incluida la opción "MENOR", que
    # toma automáticamente el que resulte más bajo—.
    porcentaje_anticipo = {
        1: parametros.anticipo_primer_anio,
        2: parametros.anticipo_segundo_anio,
    }.get(insumos.anios_declarando, parametros.anticipo_siguientes)
    pct_texto = f"{porcentaje(porcentaje_anticipo)}%"

    directo = _no_negativo(
        redondear_pesos(impuesto_neto * porcentaje_anticipo - retenciones)
    )
    formula_directo = (
        f"{pct_texto} × impuesto neto ${impuesto_neto.quantize(_CENTAVO)} − retenciones "
        f"${retenciones.quantize(_CENTAVO)}"
    )

    promedio_base = (impuesto_neto + insumos.impuesto_neto_anio_anterior) / Decimal(2)
    promedio = _no_negativo(
        redondear_pesos(promedio_base * porcentaje_anticipo - retenciones)
    )
    formula_promedio = (
        f"{pct_texto} × promedio de los dos últimos años "
        f"(${impuesto_neto.quantize(_CENTAVO)} y "
        f"${insumos.impuesto_neto_anio_anterior.quantize(_CENTAVO)}) = "
        f"${promedio_base.quantize(_CENTAVO)} − retenciones "
        f"${retenciones.quantize(_CENTAVO)}"
    )

    metodo = (insumos.metodo_anticipo or "DIRECTO").upper()
    # Sin impuesto neto del año anterior registrado, el promedio sería
    # (neto + 0) / 2: la mitad del anticipo que corresponde. Eso no es un
    # ahorro, es un dato faltante, y declararlo así expondría al contribuyente
    # a una sanción por anticipo insuficiente. Se cae al método directo.
    if (
        metodo in {"PROMEDIO", "MENOR"}
        and insumos.anios_declarando > 1
        and insumos.impuesto_neto_anio_anterior <= CERO
    ):
        liq.diagnosticos.append(
            "No hay impuesto neto del año anterior registrado, así que el método "
            "del promedio del art. 807 daría la mitad del anticipo que corresponde. "
            "Se usó el método directo; registre el impuesto neto del año anterior "
            "para poder comparar los dos procedimientos."
        )
        metodo = "DIRECTO"
    if metodo in {"PROMEDIO", "MENOR"} and insumos.anios_declarando <= 1:
        liq.diagnosticos.append(
            "Es la primera declaración, así que no hay impuesto neto del año "
            "anterior para promediar: se usó el método directo. El art. 807 habla "
            "del promedio de los dos últimos años y la DIAN discute su uso cuando "
            "no existe el año anterior."
        )
        metodo = "DIRECTO"

    if metodo == "PROMEDIO":
        anticipo, formula_anticipo = promedio, formula_promedio
    elif metodo == "MENOR":
        if promedio < directo:
            anticipo, formula_anticipo = promedio, formula_promedio
        else:
            anticipo, formula_anticipo = directo, formula_directo
        formula_anticipo += (
            f". Se escogió el menor entre el método directo (${directo}) y el del "
            f"promedio (${promedio})"
        )
    else:
        anticipo, formula_anticipo = directo, formula_directo

    R(Renglon("ANTICIPO-SIGUIENTE", "Anticipo del impuesto del año siguiente", anticipo,
              formula_anticipo, parametros.fuente_anticipo, casilla=133))

    if (
        metodo == "DIRECTO"
        and insumos.impuesto_neto_anio_anterior > CERO
        and promedio < directo
        and insumos.anios_declarando > 1
    ):
        liq.diagnosticos.append(
            f"El método del promedio del art. 807 daría un anticipo de ${promedio} en "
            f"vez de ${directo}: ${directo - promedio} menos. El contribuyente puede "
            f"escoger el procedimiento, así que conviene revisarlo."
        )

    # --- Saldo --------------------------------------------------------------
    por_impuesto = (
        impuesto_neto
        + anticipo
        - retenciones
        - insumos.anticipo_pagado_anio_anterior
        - insumos.saldo_a_favor_anio_anterior
    )
    R(Renglon("SALDO-POR-IMPUESTO", "Saldo a pagar por impuesto",
              _no_negativo(por_impuesto),
              "Casillas 129 + 133 − 130 − 131 − 132, sin sanciones", "Art. 807 ET",
              casilla=134))
    if insumos.sanciones > CERO:
        R(Renglon("SANCIONES", "Sanciones", insumos.sanciones,
                  insumos.formula_sanciones or "Sanciones liquidadas por el declarante",
                  "Arts. 639, 640 y 641 ET", casilla=135))
    neto = por_impuesto + insumos.sanciones
    saldo_a_pagar = _no_negativo(neto)
    saldo_a_favor = _no_negativo(-neto)
    R(Renglon("SALDO-A-PAGAR", "Total saldo a pagar", saldo_a_pagar,
              "Impuesto neto + anticipo del año siguiente + sanciones − retenciones − "
              "anticipo pagado el año anterior − saldo a favor del año anterior",
              "Art. 807 ET", casilla=136))
    R(Renglon("SALDO-A-FAVOR", "Total saldo a favor", saldo_a_favor,
              "Resultado negativo de la misma operación; puede solicitarse en "
              "devolución o compensación",
              "Arts. 850 y 815 ET", casilla=137))

    liq.notas.append(nota_de_numeracion(insumos.anio_gravable))
    return liq


def _slug(texto: str) -> str:
    limpio = "".join(c if c.isalnum() else "-" for c in texto.upper())
    return "-".join(p for p in limpio.split("-") if p)[:40]
