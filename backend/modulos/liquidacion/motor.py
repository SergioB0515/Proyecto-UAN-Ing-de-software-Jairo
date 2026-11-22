"""Motor de liquidación de renta, personas naturales residentes (formulario 210).

Entrada: InsumosLiquidacion + ParametrosAnuales. Salida: Liquidacion, una lista
de renglones con valor, fórmula, fuente legal y casilla.

- Funciones puras: sin base de datos, sin reloj.
- Todo importe es Decimal; se redondea solo donde la norma lo exige.
- Ningún valor del Estatuto está en este archivo: llegan en los parámetros.
- No decide: el resultado es un borrador que revisa el contador (art. 581 ET).
"""

from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple

from core.dinero import redondear_pesos
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
from core.formato import pesos

CERO = Decimal("0")
_CENTAVO = Decimal("0.01")
_MIL = Decimal("1000")

_NOMBRE_SUBCEDULA = {
    TRABAJO: "rentas de trabajo",
    SIN_VINCULO: "rentas de trabajo sin vínculo laboral",
    CAPITAL: "rentas de capital",
    NO_LABORAL: "rentas no laborales",
}


# Redondeo


# `redondear_pesos` vive en core.dinero, que es de donde lo toman todos los
# módulos. Se vuelve a exportar acá porque dentro de liquidación se usa en 18
# sitios y varios lo importan desde este módulo.


def aproximar_al_multiplo_de_mil(valor: Decimal) -> Decimal:
    """Aproxima al múltiplo de mil (art. 577 ET). Solo para el valor declarado."""
    return (valor / _MIL).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * _MIL


def _no_negativo(valor: Decimal) -> Decimal:
    return valor if valor > CERO else CERO


def porcentaje(fraccion: Decimal) -> str:
    """0.40 -> "40". Decimal.normalize() devolvería 4E+1; conserva 2,22 (art. 137)."""
    texto = f"{(fraccion * 100):f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


# Insumos


@dataclass
class ConceptoDepuracion:
    """Deducción o renta exenta solicitada.

    sujeto_a_limite_general: False para dependientes y 1 % de compras
    (art. 336 num. 5), que no entran al 40 % / 1.340 UVT.
    """

    nombre: str
    valor: Decimal
    sujeto_a_limite_general: bool = True
    fuente_legal: str = ""
    # Código de plantilla. Sin él no se aplica tope propio.
    codigo_tope: Optional[str] = None
    # Columna del 210 (casillas 41, 53, 69, 86). None: el motor la imputa en
    # orden del formulario.
    subcedula: Optional[str] = None
    # Fila: AFC/FVP/AVC (35, 47, 63, 80) e intereses de vivienda (38, 50, 66, 83)
    # tienen casilla propia.
    tipo: str = EXENTA_OTRA


@dataclass
class RentasDeTrabajo:
    """Rentas de trabajo (art. 335 ET)."""

    ingresos_brutos: Decimal = CERO
    aportes_obligatorios_salud: Decimal = CERO
    aportes_obligatorios_pension: Decimal = CERO
    otros_ingresos_no_constitutivos: Decimal = CERO

    # Honorarios sin vínculo. Art. 336 num. 4: costos y gastos o exenta del
    # art. 206 num. 10, no ambos.
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

    costo_de_ventas viene del kardex; va separado de costos_y_gastos.
    """

    ingresos_brutos: Decimal = CERO
    # Devoluciones, rebajas y descuentos (casilla 75). Solo no laborales.
    devoluciones: Decimal = CERO
    ingresos_no_constitutivos: Decimal = CERO
    costos_y_gastos: Decimal = CERO
    costo_de_ventas: Decimal = CERO
    depreciacion: Decimal = CERO
    # Costos no procedentes: efectivo sobre el límite del art. 771-5. Campo
    # aparte para no alterar las cifras del kardex ni de la depreciación.
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
    """Dividendos de residentes, según certificado de la sociedad.

    Gravados (art. 49 par. 2): primero tarifa del art. 240 (casilla 118, 35 %
    por defecto, ajustable), el remanente va a la tabla del art. 241.
    """

    no_gravados: Decimal = CERO
    gravados: Decimal = CERO
    retencion_practicada: Decimal = CERO
    tarifa_gravados: Optional[Decimal] = None


@dataclass
class GananciasOcasionales:
    """Ganancias ocasionales (arts. 299 y ss. ET)."""

    ingresos: Decimal = CERO
    costos: Decimal = CERO
    ganancia_exenta: Decimal = CERO  # venta de vivienda, art. 311-1
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
    # Sanciones (casilla 135). Las calcula sanciones.py; el motor no mira fechas.
    sanciones: Decimal = CERO
    formula_sanciones: str = ""
    anios_declarando: int = 3  # 1 = primer año, 2 = segundo, 3+ = pleno

    # Parte empresarial
    activos_depreciables: List[ActivoDepreciable] = field(default_factory=list)
    bancarizacion: InsumosBancarizacion = field(default_factory=InsumosBancarizacion)
    perdidas_compensables: List[PerdidaCompensable] = field(default_factory=list)
    comparacion_patrimonial: InsumosComparacionPatrimonial = field(
        default_factory=InsumosComparacionPatrimonial
    )

    # Anticipo: "DIRECTO", "PROMEDIO" o "MENOR".
    metodo_anticipo: str = "DIRECTO"
    impuesto_neto_anio_anterior: Decimal = CERO

    # Subcédula de la depreciación. La fija el contador.
    cedula_depreciacion: str = "NO_LABORAL"

    # Renglones y diagnósticos ya calculados por quien llama (p. ej. ventas de
    # inmuebles). Se agregan sin recalcular.
    renglones_informativos: list = field(default_factory=list)
    diagnosticos_adicionales: List[str] = field(default_factory=list)


# Resultado


@dataclass
class Renglon:
    """Valor de la liquidación con fórmula y fuente."""

    codigo: str
    nombre: str
    valor: Decimal
    formula: str = ""
    fuente_legal: str = ""
    # Casilla del 210, si aplica.
    casilla: Optional[int] = None

    @property
    def valor_declarable(self) -> Decimal:
        """Valor aproximado a mil (art. 577 ET)."""
        return aproximar_al_multiplo_de_mil(self.valor)


@dataclass
class Liquidacion:
    anio_gravable: int
    uvt: Decimal
    regimen: str
    renglones: List[Renglon] = field(default_factory=list)
    diagnosticos: List[str] = field(default_factory=list)
    notas: List[str] = field(default_factory=list)
    # Casillas de marca, sin valor (casilla 140).
    casillas_marcadas: List[int] = field(default_factory=list)

    def valor(self, codigo: str) -> Decimal:
        for renglon in self.renglones:
            if renglon.codigo == codigo:
                return renglon.valor
        return CERO


class AnioGravableNoSoportadoError(Exception):
    """Año sin parámetros. Se falla en vez de usar los de otro año."""


# Tabla de tarifas


def aplicar_tabla(
    base_pesos: Decimal, tabla: Tuple[TramoTarifa, ...], uvt: Decimal
) -> Tuple[Decimal, str, Optional[TramoTarifa]]:
    """Aplica una tabla marginal en UVT a una base en pesos.

    Calcula en UVT y convierte a pesos al final. Devuelve impuesto, fórmula y tramo.
    """
    if base_pesos <= CERO:
        return CERO, "Base gravable igual o menor a cero: impuesto 0", None

    base_uvt = base_pesos / uvt
    tramo = next((t for t in tabla if t.contiene(base_uvt)), None)
    if tramo is None:
        # Base en el tramo exento (0 a 1.090 UVT).
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
        f"{impuesto_uvt.quantize(_CENTAVO)} UVT × {pesos(uvt)}"
    )
    return impuesto, formula, tramo


# Cédula general (art. 336 ET)


def _renta_exenta_trabajo(
    insumos: InsumosLiquidacion,
    parametros: ParametrosAnuales,
    otras_restas_de_trabajo: Decimal,
) -> Tuple[Decimal, str]:
    """Renta exenta del 25 % de rentas de trabajo (art. 206 num. 10).

    Base: ingreso menos INCRNGO, deducciones y demás exentas. Tope 790 UVT.
    No aplica a honorarios con opción de costos (art. 336 num. 4).
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
        f"25% × {pesos(subtotal)} (pagos laborales depurados) = "
        f"{pesos(porcentual)}, topado en "
        f"{limite.tope_uvt} UVT = {pesos(tope)}"
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
    """Recorta cada concepto a su tope propio, antes del límite general.

    Orden obligatorio: tope propio (vivienda 1.200 UVT, prepagada 16 UVT/mes,
    voluntarias 3.800 UVT) y luego el 40 % / 1.340 UVT. Los topes compartidos
    (FVP + AFC) se recortan a prorrata dentro del grupo.
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

    # Agrupado por tope compartido; None = tope individual.
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
                        f"solicitado {pesos(concepto.valor)}, tope "
                        f"{pesos(limite)}",
                        tope.fuente_legal,
                    )
                )
                diagnosticos.append(
                    f"«{concepto.nombre}»: se solicitaron "
                    f"{pesos(concepto.valor)} y el tope propio del "
                    f"concepto es {pesos(limite)} "
                    f"({tope.fuente_legal}). Se recortaron "
                    f"{pesos(recorte)} antes de aplicar el límite "
                    f"general del art. 336."
                )
            continue

        # Tope compartido: sobre la suma del grupo.
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
                f"{pesos(solicitado)}, tope conjunto "
                f"{pesos(limite)}, repartido a prorrata",
                tope.fuente_legal,
            )
        )
        diagnosticos.append(
            f"Los conceptos que comparten el tope de "
            f"{clave.replace('_', ' ').lower()} suman "
            f"{pesos(solicitado)} y ese tope es "
            f"{pesos(limite)} ({tope.fuente_legal}). No es un tope "
            f"por concepto: se recortaron {pesos((solicitado - limite))} "
            f"repartidos a prorrata."
        )

    return ajustados, renglones, diagnosticos


def _aplicar_limite_general(
    solicitado: Decimal,
    base_del_porcentaje: Decimal,
    parametros: ParametrosAnuales,
) -> Tuple[Decimal, str, List[str]]:
    """Límite del art. 336 num. 3: min(solicitado, 40 % de la base, 1.340 UVT).

    Base: ingresos de la cédula general − INCRNGO.
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
            f"El límite del art. 336 num. 3 recortó {pesos(recorte)} "
            f"de las rentas exentas y deducciones solicitadas: se aceptaron "
            f"{pesos(aceptado)} de {pesos(solicitado)} "
            f"porque {cual} es la cifra menor. El exceso no se traslada a otros "
            f"años ni a otras cédulas."
        )

    formula = (
        f"menor entre: solicitado {pesos(solicitado)}, "
        f"40% × {pesos(base_del_porcentaje)} = {pesos(porcentual)}, "
        f"y {limite.tope_uvt} UVT = {pesos(tope)}"
    )
    return redondear_pesos(aceptado), formula, diagnosticos


def _deducciones_fuera_del_limite(
    insumos: InsumosLiquidacion, parametros: ParametrosAnuales
) -> Tuple[dict, List[Renglon]]:
    """Deducciones fuera del límite del 40 % (art. 336 num. 5).

    Dependientes (casilla 139): 72 UVT c/u, máx. 4, tope 42 + 57.
    1 % de compras con factura (casilla 28): tope 240 UVT, sin generar pérdida.
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
                    f"{parametros.deduccion_dependientes.tope_uvt} UVT × {pesos(parametros.uvt)}"
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
                    f"menor entre 1% × {pesos(insumos.compras_con_factura_electronica)} "
                    f"= {pesos(porcentual)} y {limite.tope_uvt} UVT = "
                    f"{pesos(tope)}. Requiere pago por medio electrónico y "
                    f"factura electrónica de venta con validación previa"
                ),
                fuente_legal=limite.fuente_legal,
            )
        )

    return montos, renglones


# Liquidación


def liquidar(
    insumos: InsumosLiquidacion, parametros: ParametrosAnuales
) -> Liquidacion:
    """Liquida renta y complementarios de una persona natural residente.

    Orden del Estatuto: cédula general, pensiones, dividendos, tabla del art. 241,
    ganancias ocasionales, descuentos, anticipo, saldo.
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

    # Patrimonio
    R(Renglon("PAT-BRUTO", "Total patrimonio bruto", insumos.patrimonio.patrimonio_bruto,
              "Suma de los activos poseídos a 31 de diciembre", "Arts. 261 y 267 ET",
              casilla=29))
    R(Renglon("PAT-DEUDAS", "Deudas", insumos.patrimonio.deudas,
              "Pasivos vigentes a 31 de diciembre", "Art. 283 ET", casilla=30))
    R(Renglon("PAT-LIQUIDO", "Total patrimonio líquido",
              insumos.patrimonio.patrimonio_liquido,
              "Patrimonio bruto − deudas", "Art. 282 ET", casilla=31))

    # Depreciación (arts. 128-131 y 137 ET). Sobre copias: liquidar dos veces
    # los mismos insumos (simulador) debe dar lo mismo.
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

    # Cédula general: grilla y límite del num. 3 en cedula_general.py.
    costos_cg = capital.total_costos + no_laborales.total_costos
    if trabajo.opta_por_costos_y_gastos:
        costos_cg += trabajo.costos_y_gastos_sin_vinculo_laboral

    # Bancarización (art. 771-5). El rechazo se resta de los costos de cada
    # columna, a prorrata de sus costos: la norma fija un límite global.
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
                        # La última columna absorbe el redondeo.
                        parte = rechazado_restante
                    else:
                        parte = (
                            banca.efectivo_rechazado * costos_destino / costos_cg
                        ).quantize(_CENTAVO)
                        rechazado_restante -= parte
                    destino.costos_no_procedentes += parte
                costos_cg = _no_negativo(costos_cg - banca.efectivo_rechazado)

    # Topes propios
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

    # Deducciones fuera del límite del num. 3
    fuera_calculadas, renglones_fuera = _deducciones_fuera_del_limite(insumos, parametros)
    for renglon in renglones_fuera:
        R(renglon)
    dependientes_336 = fuera_calculadas.get("DEPENDIENTES_336", CERO)
    compras_1_pct = fuera_calculadas.get("COMPRAS_1_PCT", CERO)

    # Grilla
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

    # Compensación de pérdidas. Después del límite: se compensa contra la renta
    # líquida ordinaria del ejercicio (casillas 54, 70, 87).
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

    # Totales de la cédula general, derivados de la grilla.
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

    # Renglones de la grilla con su casilla
    R(Renglon("CG-BASE-LIMITE", "Base para el límite del 40 %", cg.base_del_limite,
              "Ingresos brutos de las cuatro subcédulas − ingresos no constitutivos. "
              "Las devoluciones de la casilla 75 no se restan de esta base",
              parametros.limite_general.fuente_legal))
    for numero, nombre_fila, valor in casillas_de(cg):
        R(Renglon(f"CG-C{numero}", f"[{numero}] {nombre_fila}", valor,
                  f"Casilla {numero} del formulario 210",
                  "Arts. 335, 336, 338 y 340 ET", casilla=numero))

    # Pérdida del ejercicio: compensable en años siguientes (art. 147).
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
                f"ingresos en {pesos(perdida)}: esa parte NO se dedujo "
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

    # Casilla 140 (art. 336-1): marcar si casilla 45 > 60 % de casilla 43.
    # No cambia el impuesto.
    sin_vinculo = cg.columnas[SIN_VINCULO]
    if (
        sin_vinculo.ingresos_brutos > CERO
        and sin_vinculo.costos_y_deducciones
        > sin_vinculo.ingresos_brutos * Decimal("0.60")
    ):
        liq.casillas_marcadas.append(140)
        liq.diagnosticos.append(
            f"Los costos de las rentas de trabajo sin vínculo laboral "
            f"({pesos(sin_vinculo.costos_y_deducciones)}) superan el 60 % "
            f"de sus ingresos ({pesos(sin_vinculo.ingresos_brutos)}): hay "
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

    # Alias del total de la cédula general. La casilla 97 se emite después,
    # con la renta por comparación patrimonial.
    renta_liquida_cg = cg.casilla_93
    R(Renglon("CG-RENTA-LIQUIDA", "Renta líquida gravable de la cédula general",
              renta_liquida_cg,
              "Casilla 93: renta líquida de la cédula general menos las rentas "
              "exentas y deducciones imputables limitadas",
              "Art. 336 ET"))

    # Pensiones
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
                  f"{meses} mes(es) = {pesos(tope_pensiones)}",
                  parametros.fuente_renta_exenta_pensiones, casilla=102))
        R(Renglon("PEN-RENTA-LIQUIDA", "Renta líquida gravable de pensiones",
                  renta_liquida_pensiones, "Ingresos − no constitutivos − renta exenta",
                  "Art. 337 ET", casilla=103))

    # Dividendos
    div = insumos.dividendos
    tarifa_240 = (
        div.tarifa_gravados
        if div.tarifa_gravados is not None
        else parametros.tarifa_dividendos_gravados
    )
    impuesto_dividendos_gravados = redondear_pesos(div.gravados * tarifa_240)
    # A la tabla: no gravados + gravados menos su impuesto
    # (casilla 111 = ... + 107 + 108 − 118).
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
                  f"{porcentaje(tarifa_240)}% × {pesos(div.gravados)}. "
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

    # Ganancias ocasionales. Antes de la base: la comparación patrimonial
    # necesita la GO neta.
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
                  f"{pesos(base_go)}"
                  + (f" + {porcentaje(parametros.tarifa_ganancia_ocasional_loterias)}% × "
                     f"{pesos(go.loterias_rifas_apuestas)} (loterías, rifas y apuestas)"
                     if go.loterias_rifas_apuestas > CERO else ""),
                  parametros.fuente_ganancia_ocasional, casilla=127))

    # Base gravable y tabla del art. 241
    base_ordinaria = renta_liquida_cg + renta_liquida_pensiones + renta_liquida_dividendos

    # Renta por comparación patrimonial (arts. 236-239 ET)
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
    # Presuntiva solo contra la cédula general:
    # casilla 111 = max(97, 98) + 103 + 107 + 108 − 118.
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
                f"La renta presuntiva ({pesos(presuntiva)}) superó la renta "
                f"líquida gravable de la cédula general "
                f"({pesos(casilla_97)}) y la reemplazó en la base del "
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
    # Impuesto de renta = casilla 121 (tabla + art. 240).
    impuesto_renta = impuesto_renta + impuesto_dividendos_gravados
    R(Renglon("IMP-TOTAL-RENTA", "Total impuesto sobre las rentas líquidas gravables",
              impuesto_renta, "Casillas 116 + 117 + 118 + 119 + 120",
              parametros.fuente_tabla_renta, casilla=121))

    total_a_cargo = impuesto_renta + impuesto_go + impuesto_loterias
    R(Renglon("TOTAL-A-CARGO", "Total impuesto a cargo", total_a_cargo,
              "Impuesto sobre la renta + impuesto de ganancias ocasionales",
              "Art. 241 y arts. 313 y siguientes ET"))

    # Descuentos tributarios
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
                  f"({pesos(umbral_descuento)})",
                  parametros.descuento_dividendos.fuente_legal, casilla=124))

    # Tope: impuesto de renta (126 = 121 − 125). La GO (127) no admite descuentos.
    descuentos_solicitados = descuento_dividendos + insumos.otros_descuentos_tributarios
    descuentos = min(descuentos_solicitados, impuesto_renta)
    if descuentos < descuentos_solicitados:
        liq.diagnosticos.append(
            f"Los descuentos tributarios se recortaron a {pesos(descuentos)}: "
            f"no pueden exceder el impuesto sobre la renta y el excedente de "
            f"{pesos((descuentos_solicitados - descuentos))} se pierde."
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

    # Retenciones y anticipos
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

    # Anticipo (art. 807): directo, promedio o el menor de los dos.
    porcentaje_anticipo = {
        1: parametros.anticipo_primer_anio,
        2: parametros.anticipo_segundo_anio,
    }.get(insumos.anios_declarando, parametros.anticipo_siguientes)
    pct_texto = f"{porcentaje(porcentaje_anticipo)}%"

    directo = _no_negativo(
        redondear_pesos(impuesto_neto * porcentaje_anticipo - retenciones)
    )
    formula_directo = (
        f"{pct_texto} × impuesto neto {pesos(impuesto_neto)} − retenciones "
        f"{pesos(retenciones)}"
    )

    promedio_base = (impuesto_neto + insumos.impuesto_neto_anio_anterior) / Decimal(2)
    promedio = _no_negativo(
        redondear_pesos(promedio_base * porcentaje_anticipo - retenciones)
    )
    formula_promedio = (
        f"{pct_texto} × promedio de los dos últimos años "
        f"({pesos(impuesto_neto)} y "
        f"{pesos(insumos.impuesto_neto_anio_anterior)}) = "
        f"{pesos(promedio_base)} − retenciones "
        f"{pesos(retenciones)}"
    )

    metodo = (insumos.metodo_anticipo or "DIRECTO").upper()
    # Sin impuesto neto del año anterior, el promedio daría la mitad: se usa
    # el método directo.
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
            f". Se escogió el menor entre el método directo ({pesos(directo)}) y el del "
            f"promedio ({pesos(promedio)})"
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
            f"El método del promedio del art. 807 daría un anticipo de {pesos(promedio)} en "
            f"vez de {pesos(directo)}: {pesos(directo - promedio)} menos. El contribuyente puede "
            f"escoger el procedimiento, así que conviene revisarlo."
        )

    # Saldo
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

    liq.renglones.extend(insumos.renglones_informativos)
    liq.diagnosticos.extend(insumos.diagnosticos_adicionales)
    liq.notas.append(nota_de_numeracion(insumos.anio_gravable))
    return liq


def _slug(texto: str) -> str:
    limpio = "".join(c if c.isalnum() else "-" for c in texto.upper())
    return "-".join(p for p in limpio.split("-") if p)[:40]
