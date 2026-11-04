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

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple

from ..parametros.tablas_oficiales import ParametrosAnuales, TramoTarifa
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
    ingresos_no_constitutivos: Decimal = CERO
    costos_y_gastos: Decimal = CERO
    costo_de_ventas: Decimal = CERO
    depreciacion: Decimal = CERO

    @property
    def total_costos(self) -> Decimal:
        return self.costos_y_gastos + self.costo_de_ventas + self.depreciacion


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
    retención. El motor no deduce el impuesto societario por su cuenta: la
    certificación es la fuente y asumir una tarifa produciría cifras falsas.
    """

    no_gravados: Decimal = CERO
    gravados: Decimal = CERO
    retencion_practicada: Decimal = CERO


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
) -> Tuple[Decimal, List[Renglon]]:
    """Deducciones que la ley dejó por fuera del límite del 40 %.

    Son dos: la deducción por dependientes (72 UVT por cada uno, hasta cuatro,
    adicional al límite general) y el 1 % de las compras soportadas en factura
    electrónica, topado en 240 UVT (art. 336 num. 5).
    """
    renglones: List[Renglon] = []
    total = CERO

    dependientes = max(0, min(insumos.numero_dependientes, parametros.max_dependientes))
    if dependientes:
        valor = redondear_pesos(
            Decimal(dependientes) * (parametros.deduccion_dependientes.tope_uvt or CERO) * parametros.uvt
        )
        total += valor
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
        total += valor
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

    return total, renglones


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
              "Suma de los activos poseídos a 31 de diciembre", "Arts. 261 y 267 ET"))
    R(Renglon("PAT-DEUDAS", "Deudas", insumos.patrimonio.deudas,
              "Pasivos vigentes a 31 de diciembre", "Art. 283 ET"))
    R(Renglon("PAT-LIQUIDO", "Total patrimonio líquido",
              insumos.patrimonio.patrimonio_liquido,
              "Patrimonio bruto − deudas", "Art. 282 ET"))

    # --- Depreciación (arts. 128 a 131 y 137 ET) --------------------------
    trabajo, capital, no_laborales = insumos.trabajo, insumos.capital, insumos.no_laborales

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

    # --- Cédula general: ingresos e INCRNGO -------------------------------
    ingresos_cg = (
        trabajo.total_ingresos + capital.ingresos_brutos + no_laborales.ingresos_brutos
    )
    incrngo_cg = (
        trabajo.total_incrngo
        + capital.ingresos_no_constitutivos
        + no_laborales.ingresos_no_constitutivos
    )
    # Base del 40 %: ingresos menos INCRNGO, antes de costos y gastos.
    base_limite = _no_negativo(ingresos_cg - incrngo_cg)

    R(Renglon("CG-INGRESOS", "Ingresos brutos de la cédula general", ingresos_cg,
              "Rentas de trabajo + rentas de capital + rentas no laborales. "
              "No incluye dividendos ni ganancias ocasionales",
              "Arts. 335, 338 y 340 ET"))
    R(Renglon("CG-INCRNGO", "Ingresos no constitutivos de renta ni ganancia ocasional",
              incrngo_cg,
              "Aportes obligatorios a salud y pensión y demás conceptos no constitutivos",
              "Arts. 55 y 56 ET"))
    R(Renglon("CG-BASE-LIMITE", "Base para el límite del 40 %", base_limite,
              "Ingresos de la cédula general − ingresos no constitutivos",
              parametros.limite_general.fuente_legal))

    # --- Renta líquida por subcédula --------------------------------------
    #
    # Se calcula subcédula por subcédula y no en bloque, porque el art. 330
    # exige que una pérdida solo se compense contra rentas del mismo tipo. Sin
    # este detalle, la compensación se aplicaría contra el total y daría un
    # impuesto menor al que corresponde.
    costos_cg = capital.total_costos + no_laborales.total_costos
    if trabajo.opta_por_costos_y_gastos:
        costos_cg += trabajo.costos_y_gastos_sin_vinculo_laboral

    R(Renglon("CG-COSTOS", "Costos y gastos procedentes", costos_cg,
              "Imputables a rentas de capital y no laborales, incluidos el costo de "
              "ventas del inventario y la depreciación. Los de honorarios sin vínculo "
              "laboral solo si se optó por ellos en vez de la renta exenta del "
              "art. 206 num. 10",
              "Art. 336 num. 4 ET"))
    if capital.costo_de_ventas + no_laborales.costo_de_ventas > CERO:
        R(Renglon("CG-COSTO-VENTAS", "Costo de ventas del inventario",
                  capital.costo_de_ventas + no_laborales.costo_de_ventas,
                  "Calculado por el kardex del módulo de inventario con el método de "
                  "costeo de cada producto",
                  "Arts. 62 y 66 ET"))

    # Las rentas líquidas negativas se truncan en cero, pero el exceso no
    # desaparece: es una pérdida fiscal del ejercicio y el art. 147 permite
    # compensarla en los doce años siguientes. Si no se reportara, el contador
    # vería la deducción en el borrador, no la vería restada en ninguna parte y
    # tampoco sabría que tiene una pérdida que registrar.
    perdidas_del_ejercicio: dict = {}

    def _renta_subcedula(tipo: str, ingresos: Decimal, incrngo: Decimal, costos: Decimal) -> Decimal:
        bruta = ingresos - incrngo - costos
        if bruta < CERO:
            perdidas_del_ejercicio[tipo] = -bruta
        return _no_negativo(bruta)

    renta_por_tipo: dict = {}
    if trabajo.opta_por_costos_y_gastos:
        renta_por_tipo["TRABAJO_SIN_VINCULO"] = _renta_subcedula(
            "TRABAJO_SIN_VINCULO",
            trabajo.ingresos_sin_vinculo_laboral,
            CERO,
            trabajo.costos_y_gastos_sin_vinculo_laboral,
        )
        renta_trabajo_laboral = _no_negativo(
            trabajo.ingresos_brutos - trabajo.total_incrngo
        )
    else:
        renta_trabajo_laboral = _no_negativo(
            trabajo.ingresos_brutos
            + trabajo.ingresos_sin_vinculo_laboral
            - trabajo.total_incrngo
        )
    renta_por_tipo["CAPITAL"] = _renta_subcedula(
        "CAPITAL",
        capital.ingresos_brutos,
        capital.ingresos_no_constitutivos,
        capital.total_costos,
    )
    renta_por_tipo["NO_LABORAL"] = _renta_subcedula(
        "NO_LABORAL",
        no_laborales.ingresos_brutos,
        no_laborales.ingresos_no_constitutivos,
        no_laborales.total_costos,
    )

    for tipo, perdida in perdidas_del_ejercicio.items():
        R(Renglon(f"CG-PERDIDA-EJERCICIO-{tipo}",
                  f"Pérdida del ejercicio — {tipo.replace('_', ' ').lower()}",
                  perdida,
                  "Los costos y deducciones de esta subcédula superaron sus ingresos. "
                  "La renta líquida se trunca en cero y el exceso queda como pérdida",
                  "Arts. 147 y 330 ET"))
        liq.diagnosticos.append(
            f"Los costos imputados a {tipo.replace('_', ' ').lower()} superan sus "
            f"ingresos en ${perdida.quantize(_CENTAVO)}: esa parte NO se dedujo este "
            f"año. Regístrela como pérdida fiscal de {insumos.anio_gravable} para "
            f"poder compensarla en los próximos {parametros.anios_compensacion_perdidas} "
            f"años, o revise si la depreciación y los costos están imputados a la "
            f"subcédula correcta."
        )

    # --- Compensación de pérdidas de años anteriores ----------------------
    compensacion = calcular_compensacion_perdidas(
        insumos.perdidas_compensables, renta_por_tipo, insumos.anio_gravable, parametros
    )
    liq.diagnosticos.extend(compensacion.diagnosticos)
    for nombre, valor, formula in compensacion.detalle:
        R(Renglon(f"CG-PERD-{_slug(nombre)}", nombre, valor, formula,
                  parametros.fuente_compensacion_perdidas))
    total_compensado = sum(compensacion.por_tipo.values(), CERO)
    if total_compensado > CERO:
        R(Renglon("CG-COMPENSACION", "Compensación de pérdidas de años anteriores",
                  total_compensado,
                  "Imputadas contra la renta líquida del mismo tipo de renta; las "
                  "rentas de trabajo con vínculo laboral no admiten compensación",
                  parametros.fuente_compensacion_perdidas))

    renta_liquida_antes = renta_trabajo_laboral + sum(
        _no_negativo(renta - compensacion.por_tipo.get(tipo, CERO))
        for tipo, renta in renta_por_tipo.items()
    )

    # --- Bancarización (art. 771-5 ET) ------------------------------------
    #
    # El efectivo rechazado se devuelve a la renta líquida: se restó como costo
    # y la norma no lo acepta. Se muestra como renglón propio en vez de
    # descontarlo del renglón de costos, para que el contador vea cuánto perdió
    # por pagar en efectivo y pueda cambiar la práctica el año siguiente.
    banca = calcular_bancarizacion(insumos.bancarizacion, costos_cg, parametros)
    liq.diagnosticos.extend(banca.diagnosticos)
    if banca.aplica:
        R(Renglon("CG-EFECTIVO-ACEPTADO", "Pagos en efectivo aceptados",
                  banca.efectivo_aceptado, banca.formula,
                  parametros.bancarizacion.fuente_legal))
        if banca.efectivo_rechazado > CERO:
            R(Renglon("CG-EFECTIVO-RECHAZADO",
                      "Pagos en efectivo no deducibles (se devuelven a la renta)",
                      banca.efectivo_rechazado,
                      "Exceso sobre el límite del art. 771-5: se suma de vuelta a la "
                      "renta líquida porque no es un costo procedente",
                      parametros.bancarizacion.fuente_legal))
            renta_liquida_antes += banca.efectivo_rechazado

    R(Renglon("CG-RL-ANTES", "Renta líquida antes de rentas exentas y deducciones",
              renta_liquida_antes,
              "Suma de la renta líquida de cada subcédula, menos las pérdidas "
              "compensadas, más los pagos en efectivo no deducibles",
              "Art. 336 ET"))

    # --- Conceptos sujetos al límite --------------------------------------
    limitables = [c for c in insumos.conceptos_depuracion if c.sujeto_a_limite_general]
    no_limitables_informados = [
        c for c in insumos.conceptos_depuracion if not c.sujeto_a_limite_general
    ]
    suma_limitables_informados = sum((c.valor for c in limitables), CERO)

    exenta_trabajo, formula_exenta = _renta_exenta_trabajo(
        insumos, parametros, suma_limitables_informados
    )
    if exenta_trabajo > CERO:
        R(Renglon("CG-EXENTA-25", "Renta exenta del 25 % de rentas de trabajo",
                  exenta_trabajo, formula_exenta,
                  parametros.renta_exenta_trabajo.fuente_legal))

    for concepto in limitables:
        R(Renglon(f"CG-SOL-{_slug(concepto.nombre)}", concepto.nombre, concepto.valor,
                  "Solicitado por el contribuyente, sujeto al límite del art. 336 num. 3",
                  concepto.fuente_legal))

    solicitado = suma_limitables_informados + exenta_trabajo
    aceptado, formula_limite, diag_limite = _aplicar_limite_general(
        solicitado, base_limite, parametros
    )
    liq.diagnosticos.extend(diag_limite)
    R(Renglon("CG-EXENTAS-LIMITADAS",
              "Rentas exentas y deducciones imputables (limitadas)", aceptado,
              formula_limite, parametros.limite_general.fuente_legal))

    # --- Conceptos fuera del límite ---------------------------------------
    fuera_calculadas, renglones_fuera = _deducciones_fuera_del_limite(insumos, parametros)
    for renglon in renglones_fuera:
        R(renglon)
    suma_no_limitables_informados = sum((c.valor for c in no_limitables_informados), CERO)
    for concepto in no_limitables_informados:
        R(Renglon(f"CG-NOLIM-{_slug(concepto.nombre)}", concepto.nombre, concepto.valor,
                  "No sujeto al límite del art. 336 num. 3", concepto.fuente_legal))
    fuera_del_limite = fuera_calculadas + suma_no_limitables_informados

    renta_liquida_cg = _no_negativo(renta_liquida_antes - aceptado - fuera_del_limite)
    R(Renglon("CG-RENTA-LIQUIDA", "Renta líquida gravable de la cédula general",
              renta_liquida_cg,
              "Renta líquida − exentas y deducciones limitadas − deducciones fuera del límite",
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
                  "Mesadas y demás pagos pensionales del año", "Art. 337 ET"))
        R(Renglon("PEN-EXENTA", "Renta exenta de pensiones", exenta_pensiones,
                  f"Topada en {parametros.renta_exenta_pensiones_uvt_mensual} UVT × "
                  f"{meses} mes(es) = ${tope_pensiones.quantize(_CENTAVO)}",
                  parametros.fuente_renta_exenta_pensiones))
        R(Renglon("PEN-RENTA-LIQUIDA", "Renta líquida gravable de pensiones",
                  renta_liquida_pensiones, "Ingresos − no constitutivos − renta exenta",
                  "Art. 337 ET"))

    # --- Dividendos --------------------------------------------------------
    div = insumos.dividendos
    renta_liquida_dividendos = div.no_gravados + div.gravados
    if renta_liquida_dividendos > CERO:
        R(Renglon("DIV-RENTA-LIQUIDA", "Renta líquida cedular de dividendos y participaciones",
                  renta_liquida_dividendos,
                  "Dividendos no gravados + gravados, según el certificado de la sociedad. "
                  "Integran la base de la tabla del art. 241",
                  "Arts. 242 y 331 ET, modificados por la Ley 2277 de 2022"))
        liq.notas.append(
            "Los dividendos se integraron completos a la base del art. 241 y el "
            "impuesto societario y la retención se imputan como retenciones. Existe "
            "una lectura alternativa que integra solo el remanente de los dividendos "
            "gravados después del impuesto societario; cambia el resultado, así que "
            "confírmala contra el certificado y la doctrina vigente antes de presentar."
        )

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
                  parametros.fuente_ganancia_ocasional))

    # --- Base gravable y tabla del art. 241 --------------------------------
    base_ordinaria = renta_liquida_cg + renta_liquida_pensiones + renta_liquida_dividendos

    # --- Renta por comparación patrimonial (arts. 236 a 239 ET) -----------
    comparacion = calcular_comparacion_patrimonial(
        insumos.comparacion_patrimonial,
        insumos.patrimonio.patrimonio_liquido,
        base_ordinaria,
        aceptado + exenta_pensiones,
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
                      "Art. 236 ET"))

    presuntiva = insumos.renta_presuntiva
    base_241 = max(base_ordinaria + renta_comparacion, presuntiva)
    if presuntiva > CERO:
        R(Renglon("RENTA-PRESUNTIVA", "Renta presuntiva", presuntiva,
                  f"Tarifa vigente: {porcentaje(parametros.tarifa_renta_presuntiva)}%",
                  parametros.fuente_renta_presuntiva))
        if presuntiva > base_ordinaria + renta_comparacion:
            liq.diagnosticos.append(
                f"La renta presuntiva (${presuntiva.quantize(_CENTAVO)}) superó la renta "
                f"ordinaria (${(base_ordinaria + renta_comparacion).quantize(_CENTAVO)}) "
                f"y pasó a ser la base del impuesto."
            )

    R(Renglon("BASE-GRAVABLE", "Renta líquida gravable total", base_241,
              "Mayor entre la suma de las rentas líquidas cedulares (más la renta por "
              "comparación patrimonial, si se aceptó) y la renta presuntiva",
              "Arts. 241, 331 y 188 ET"))

    impuesto_renta, formula_impuesto, _ = aplicar_tabla(base_241, parametros.tabla_renta, uvt)
    R(Renglon("IMP-RENTA", "Impuesto sobre la renta líquida gravable", impuesto_renta,
              formula_impuesto, parametros.fuente_tabla_renta))

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
                  parametros.descuento_dividendos.fuente_legal))

    descuentos_solicitados = descuento_dividendos + insumos.otros_descuentos_tributarios
    descuentos = min(descuentos_solicitados, total_a_cargo)
    if descuentos < descuentos_solicitados:
        liq.diagnosticos.append(
            f"Los descuentos tributarios se recortaron a ${descuentos.quantize(_CENTAVO)}: "
            f"no pueden exceder el impuesto a cargo y el excedente de "
            f"${(descuentos_solicitados - descuentos).quantize(_CENTAVO)} se pierde."
        )
    R(Renglon("TOTAL-DESCUENTOS", "Total descuentos tributarios", descuentos,
              "Limitados al impuesto a cargo", "Arts. 254-1 y 259 ET"))

    impuesto_neto = _no_negativo(total_a_cargo - descuentos)
    R(Renglon("IMP-NETO", "Impuesto neto de renta", impuesto_neto,
              "Total impuesto a cargo − descuentos tributarios", "Art. 259 ET"))

    # --- Retenciones y anticipos -------------------------------------------
    retenciones = (
        insumos.retenciones_en_la_fuente + div.retencion_practicada + go.retenciones
    )
    R(Renglon("RETENCIONES", "Total retenciones en la fuente", retenciones,
              "Retenciones del año, incluidas las de dividendos y ganancias ocasionales",
              "Art. 373 ET"))

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
              formula_anticipo, parametros.fuente_anticipo))

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
    neto = (
        impuesto_neto
        + anticipo
        - retenciones
        - insumos.anticipo_pagado_anio_anterior
        - insumos.saldo_a_favor_anio_anterior
    )
    saldo_a_pagar = _no_negativo(neto)
    saldo_a_favor = _no_negativo(-neto)
    R(Renglon("SALDO-A-PAGAR", "Saldo a pagar por impuesto", saldo_a_pagar,
              "Impuesto neto + anticipo del año siguiente − retenciones − anticipo "
              "pagado el año anterior − saldo a favor del año anterior",
              "Art. 807 ET"))
    R(Renglon("SALDO-A-FAVOR", "Total saldo a favor", saldo_a_favor,
              "Resultado negativo de la misma operación; puede solicitarse en "
              "devolución o compensación",
              "Arts. 850 y 815 ET"))

    liq.notas.append(
        "Los renglones llevan códigos propios, no los números impresos del "
        "formulario 210: esos los fija la resolución de la DIAN que prescribe el "
        "formulario de cada año gravable y hay que confirmarlos antes de transcribir."
    )
    return liq


def _slug(texto: str) -> str:
    limpio = "".join(c if c.isalnum() else "-" for c in texto.upper())
    return "-".join(p for p in limpio.split("-") if p)[:40]
