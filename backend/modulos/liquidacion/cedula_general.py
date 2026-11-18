"""Grilla de la cédula general del formulario 210 (casillas 32 a 97).

Cuatro columnas: trabajo, trabajo sin vínculo, capital, no laborales.
Fuente: instructivo oficial del formulario 210.

- Honorarios: columna sin vínculo (43) si opta por costos y gastos (art. 336
  num. 4); si no, columna de trabajo (32) con la exenta del 25 %.
- Límite del art. 336 num. 3: uno para toda la cédula, repartido en cascada.
- Dependientes (139) y 1 % de compras (28) van directo a la casilla 92.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..parametros.tablas_oficiales import ParametrosAnuales
from .formulario_210 import SUBCEDULAS, casilla_de_subcedula
from core.formato import pesos

CERO = Decimal("0")
_CENTAVO = Decimal("0.01")

TRABAJO, SIN_VINCULO, CAPITAL, NO_LABORAL = SUBCEDULAS

# Tipo de concepto: define la fila de la columna.
EXENTA_AFC = "EXENTA_AFC"
EXENTA_OTRA = "EXENTA_OTRA"
DEDUCCION_VIVIENDA = "DEDUCCION_VIVIENDA"
DEDUCCION_OTRA = "DEDUCCION_OTRA"

_NOMBRE_COLUMNA = {
    TRABAJO: "rentas de trabajo",
    SIN_VINCULO: "rentas de trabajo sin vínculo laboral",
    CAPITAL: "rentas de capital",
    NO_LABORAL: "rentas no laborales",
}

_FILA_POR_TIPO = {
    EXENTA_AFC: "Rentas exentas — aportes voluntarios AFC, FVP y AVC",
    EXENTA_OTRA: "Rentas exentas — otras rentas exentas",
    DEDUCCION_VIVIENDA: "Deducciones imputables — intereses de vivienda",
    DEDUCCION_OTRA: "Deducciones imputables — otras deducciones imputables",
}


def _no_negativo(valor: Decimal) -> Decimal:
    return valor if valor > CERO else CERO


def porcentaje_legible(fraccion: Decimal) -> str:
    """0.40 -> "40". Decimal.normalize() devolvería 4E+1."""
    texto = f"{(fraccion * 100):f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


@dataclass
class Columna:
    """Una columna de la grilla."""

    subcedula: str
    ingresos_brutos: Decimal = CERO
    devoluciones: Decimal = CERO
    ingresos_no_constitutivos: Decimal = CERO
    costos_y_deducciones: Decimal = CERO
    rentas_pasivas_ece: Decimal = CERO
    exenta_afc: Decimal = CERO
    exenta_otra: Decimal = CERO
    deduccion_vivienda: Decimal = CERO
    deduccion_otra: Decimal = CERO
    # Exentas fuera del límite del num. 3 (art. 206 nums. 6-9, 206-1, 207-2
    # nums. 3-4, CDI, Decisión 578). Misma fila, no consumen el 40 %.
    sin_limite: Decimal = CERO
    limitadas: Decimal = CERO
    compensaciones: Decimal = CERO

    @property
    def renta_liquida(self) -> Decimal:
        return _no_negativo(
            self.ingresos_brutos
            + self.rentas_pasivas_ece
            - self.devoluciones
            - self.ingresos_no_constitutivos
            - self.costos_y_deducciones
        )

    @property
    def perdida_liquida(self) -> Decimal:
        return _no_negativo(
            self.devoluciones
            + self.ingresos_no_constitutivos
            + self.costos_y_deducciones
            - self.ingresos_brutos
            - self.rentas_pasivas_ece
        )

    @property
    def total_rentas_exentas(self) -> Decimal:
        return self.exenta_afc + self.exenta_otra

    @property
    def total_deducciones(self) -> Decimal:
        return self.deduccion_vivienda + self.deduccion_otra

    @property
    def solicitado(self) -> Decimal:
        """Total solicitado, con y sin límite."""
        return self.total_rentas_exentas + self.total_deducciones

    @property
    def solicitado_limitable(self) -> Decimal:
        """Lo que consume el cupo del 40 % / 1.340 UVT."""
        return _no_negativo(self.solicitado - self.sin_limite)

    @property
    def renta_liquida_ordinaria_ejercicio(self) -> Decimal:
        return _no_negativo(self.renta_liquida - self.limitadas)

    @property
    def renta_liquida_ordinaria(self) -> Decimal:
        return _no_negativo(
            self.renta_liquida_ordinaria_ejercicio - self.compensaciones
        )


@dataclass
class ResultadoCedulaGeneral:
    columnas: Dict[str, Columna]
    base_del_limite: Decimal = CERO
    limitadas_total: Decimal = CERO
    # Casilla 139. Tope: casillas 42 + 57.
    deduccion_dependientes: Decimal = CERO
    # Casilla 28. Fuera del límite del num. 3; no puede generar pérdida.
    deduccion_compras: Decimal = CERO
    rentas_gravables: Decimal = CERO
    compensacion_2018_y_anteriores: Decimal = CERO
    compensacion_exceso_presuntiva: Decimal = CERO
    diagnosticos: List[str] = field(default_factory=list)

    @property
    def casilla_91(self) -> Decimal:
        """Casilla 91 = Σ(41, 42, 53, 57, 69, 73, 86, 90)."""
        return sum(
            (c.limitadas + c.renta_liquida_ordinaria for c in self.columnas.values()),
            CERO,
        )

    @property
    def casilla_92(self) -> Decimal:
        """Casilla 92 = 28 + 41 + 53 + 69 + 86 + 139."""
        return (
            self.deduccion_compras
            + self.limitadas_total
            + self.deduccion_dependientes
        )

    @property
    def casilla_93(self) -> Decimal:
        """Casilla 93 = 91 − 92."""
        return _no_negativo(self.casilla_91 - self.casilla_92)

    @property
    def casilla_97(self) -> Decimal:
        """Casilla 97 = 93 + 96 − 94 − 95."""
        return _no_negativo(
            self.casilla_93
            + self.rentas_gravables
            - self.compensacion_2018_y_anteriores
            - self.compensacion_exceso_presuntiva
        )


def _imputar_automaticamente(
    columnas: Dict[str, Columna], valor: Decimal
) -> List[Tuple[Columna, Decimal]]:
    """Imputa un concepto sin subcédula, llenando columnas en orden del formulario.

    Cada columna recibe hasta su renta líquida menos lo ya solicitado. El
    remanente va a la última columna con renta para que quede visible.
    """
    reparto: List[Tuple[Columna, Decimal]] = []
    restante = valor
    con_renta = [columnas[s] for s in SUBCEDULAS if columnas[s].renta_liquida > CERO]
    for columna in con_renta:
        if restante <= CERO:
            break
        espacio = _no_negativo(columna.renta_liquida - columna.solicitado)
        parte = min(restante, espacio)
        if parte > CERO:
            reparto.append((columna, parte))
            restante -= parte
    if restante > CERO:
        destino = con_renta[-1] if con_renta else columnas[TRABAJO]
        reparto.append((destino, restante))
    return reparto


def _repartir_en_cascada(
    columnas: Dict[str, Columna], aceptado: Decimal
) -> List[str]:
    """Reparte lo aceptado en cascada: trabajo, sin vínculo, capital, no laborales.

    Orden del instructivo del 210. Prorratear da el mismo impuesto pero casillas
    distintas a las de la DIAN. Techo por columna: lo solicitado y su renta
    líquida + rentas pasivas ECE; el exceso se pierde y se informa.
    """
    diagnosticos: List[str] = []
    saldo = aceptado
    for subcedula in SUBCEDULAS:
        columna = columnas[subcedula]
        if saldo <= CERO:
            columna.limitadas = CERO
            continue
        techo_renta = columna.renta_liquida + columna.rentas_pasivas_ece
        asignado = min(saldo, columna.solicitado, techo_renta)
        columna.limitadas = asignado
        saldo -= asignado
        if columna.solicitado > techo_renta and min(saldo + asignado, columna.solicitado) > techo_renta:
            diagnosticos.append(
                f"En {_NOMBRE_COLUMNA[subcedula]} las rentas exentas y deducciones "
                f"solicitadas ({pesos(columna.solicitado)}) superan la "
                f"renta líquida de esa misma columna "
                f"({pesos(techo_renta)}): el formulario no permite "
                f"imputar más de la renta líquida de la columna, así que "
                f"{pesos((columna.solicitado - techo_renta))} no se "
                f"restan en ninguna parte. Revise si esas deducciones corresponden "
                f"realmente a esta subcédula."
            )
    return diagnosticos


def depurar(
    trabajo,
    capital,
    no_laborales,
    conceptos,
    exenta_25_por_ciento: Decimal,
    dependientes: Decimal,
    compras_1_por_ciento: Decimal,
    rentas_gravables: Decimal,
    parametros: ParametrosAnuales,
) -> ResultadoCedulaGeneral:
    """Arma la grilla y aplica el límite del art. 336 num. 3."""
    columnas = {s: Columna(subcedula=s) for s in SUBCEDULAS}

    # Rentas de trabajo. Honorarios aparte solo si opta por costos (art. 336 num. 4).
    col_trabajo = columnas[TRABAJO]
    col_trabajo.ingresos_brutos = trabajo.ingresos_brutos
    col_trabajo.ingresos_no_constitutivos = trabajo.total_incrngo
    if trabajo.opta_por_costos_y_gastos:
        col_sin_vinculo = columnas[SIN_VINCULO]
        col_sin_vinculo.ingresos_brutos = trabajo.ingresos_sin_vinculo_laboral
        col_sin_vinculo.costos_y_deducciones = trabajo.costos_y_gastos_sin_vinculo_laboral
    else:
        col_trabajo.ingresos_brutos += trabajo.ingresos_sin_vinculo_laboral

    # Rentas de capital y no laborales.
    columnas[CAPITAL].ingresos_brutos = capital.ingresos_brutos
    columnas[CAPITAL].ingresos_no_constitutivos = capital.ingresos_no_constitutivos
    columnas[CAPITAL].costos_y_deducciones = capital.total_costos
    columnas[NO_LABORAL].ingresos_brutos = no_laborales.ingresos_brutos
    columnas[NO_LABORAL].devoluciones = getattr(no_laborales, "devoluciones", CERO)
    columnas[NO_LABORAL].ingresos_no_constitutivos = no_laborales.ingresos_no_constitutivos
    columnas[NO_LABORAL].costos_y_deducciones = no_laborales.total_costos

    resultado = ResultadoCedulaGeneral(columnas=columnas)

    # Conceptos. Se respeta la subcédula fijada por el contador; sin ella se
    # imputa por orden, porque una columna no puede restar más que su renta líquida.
    for concepto in conceptos:
        if concepto.subcedula:
            destinos = [(columnas[concepto.subcedula], concepto.valor)]
        else:
            destinos = _imputar_automaticamente(columnas, concepto.valor)
        for destino, parte in destinos:
            if parte <= CERO:
                continue
            if not concepto.sujeto_a_limite_general:
                destino.sin_limite += parte
            if concepto.tipo == EXENTA_AFC:
                destino.exenta_afc += parte
            elif concepto.tipo == DEDUCCION_VIVIENDA:
                destino.deduccion_vivienda += parte
            elif concepto.tipo == DEDUCCION_OTRA:
                destino.deduccion_otra += parte
            else:
                destino.exenta_otra += parte

    # Exenta del 25 %: siempre rentas de trabajo.
    col_trabajo.exenta_otra += exenta_25_por_ciento

    # Límite del num. 3. Base: ingresos brutos + rentas pasivas ECE − INCRNGO.
    # Las devoluciones (casilla 75) no se restan: el instructivo no las incluye.
    ingresos_cg = sum(
        (c.ingresos_brutos + c.rentas_pasivas_ece for c in columnas.values()), CERO
    )
    incrngo_cg = sum((c.ingresos_no_constitutivos for c in columnas.values()), CERO)
    resultado.base_del_limite = _no_negativo(ingresos_cg - incrngo_cg)

    limite = parametros.limite_general
    solicitado_limitable = sum(
        (c.solicitado_limitable for c in columnas.values()), CERO
    )
    porcentual = resultado.base_del_limite * (limite.porcentaje or CERO)
    tope = (limite.tope_uvt or CERO) * parametros.uvt
    aceptado_limitable = min(solicitado_limitable, porcentual, tope)

    # Exentas fuera del límite: se suman sobre el 40 %.
    aceptado = aceptado_limitable + sum(
        (c.sin_limite for c in columnas.values()), CERO
    )

    diag_cascada = _repartir_en_cascada(columnas, aceptado)
    resultado.diagnosticos.extend(diag_cascada)
    resultado.limitadas_total = sum((c.limitadas for c in columnas.values()), CERO)

    if aceptado_limitable < solicitado_limitable:
        cual = (
            f"el {porcentaje_legible(limite.porcentaje)} % de los ingresos depurados"
            if porcentual <= tope
            else f"el tope de {limite.tope_uvt} UVT"
        )
        resultado.diagnosticos.append(
            f"El límite del art. 336 num. 3 recortó "
            f"{pesos((solicitado_limitable - aceptado_limitable))} de las "
            f"rentas exentas y deducciones solicitadas: se aceptaron "
            f"{pesos(aceptado_limitable)} de "
            f"{pesos(solicitado_limitable)} porque {cual} es la cifra "
            f"menor. El exceso no se traslada a otros años ni a otras cédulas."
        )

    # Casilla 139: tope en 42 + 57.
    techo_dependientes = (
        columnas[TRABAJO].renta_liquida_ordinaria
        + columnas[SIN_VINCULO].renta_liquida_ordinaria
    )
    resultado.deduccion_dependientes = min(dependientes, techo_dependientes)
    if dependientes > resultado.deduccion_dependientes:
        resultado.diagnosticos.append(
            f"La adición por dependientes de la casilla 139 se limitó a "
            f"{pesos(resultado.deduccion_dependientes)}: el instructivo "
            f"no permite que exceda la renta líquida ordinaria de las rentas de "
            f"trabajo (casillas 42 y 57). Se solicitaron "
            f"{pesos(dependientes)}."
        )

    # Casilla 28: tope en la renta líquida ordinaria restante.
    ordinarias = sum((c.renta_liquida_ordinaria for c in columnas.values()), CERO)
    techo_compras = _no_negativo(ordinarias - resultado.deduccion_dependientes)
    resultado.deduccion_compras = min(compras_1_por_ciento, techo_compras)
    if compras_1_por_ciento > resultado.deduccion_compras:
        resultado.diagnosticos.append(
            f"La deducción del 1 % de compras con factura electrónica se limitó a "
            f"{pesos(resultado.deduccion_compras)}: el art. 336 num. 5 "
            f"no la sujeta al límite del 40 %, pero no puede dar lugar a pérdidas. Se "
            f"solicitaron {pesos(compras_1_por_ciento)}."
        )

    resultado.rentas_gravables = rentas_gravables
    return resultado


def casillas_de(resultado: ResultadoCedulaGeneral) -> List[Tuple[int, str, Decimal]]:
    """Celdas con valor distinto de cero: (casilla, fila, valor)."""
    filas = [
        ("Ingresos brutos", lambda c: c.ingresos_brutos),
        ("Devoluciones, rebajas y descuentos", lambda c: c.devoluciones),
        ("Ingresos no constitutivos de renta", lambda c: c.ingresos_no_constitutivos),
        ("Costos y deducciones procedentes", lambda c: c.costos_y_deducciones),
        ("Renta líquida", lambda c: c.renta_liquida),
        ("Rentas líquidas pasivas — ECE", lambda c: c.rentas_pasivas_ece),
        ("Rentas exentas — aportes voluntarios AFC, FVP y AVC", lambda c: c.exenta_afc),
        ("Rentas exentas — otras rentas exentas", lambda c: c.exenta_otra),
        ("Total rentas exentas", lambda c: c.total_rentas_exentas),
        ("Deducciones imputables — intereses de vivienda", lambda c: c.deduccion_vivienda),
        ("Deducciones imputables — otras deducciones imputables", lambda c: c.deduccion_otra),
        ("Total deducciones imputables", lambda c: c.total_deducciones),
        ("Rentas exentas y/o deducciones imputables (limitadas)", lambda c: c.limitadas),
        ("Renta líquida ordinaria del ejercicio", lambda c: c.renta_liquida_ordinaria_ejercicio),
        ("Pérdida líquida del ejercicio", lambda c: c.perdida_liquida),
        ("Compensaciones por pérdidas", lambda c: c.compensaciones),
        ("Renta líquida ordinaria", lambda c: c.renta_liquida_ordinaria),
    ]
    salida: List[Tuple[int, str, Decimal]] = []
    for nombre, obtener in filas:
        for subcedula in SUBCEDULAS:
            casilla = casilla_de_subcedula(nombre, subcedula)
            if casilla is None:
                continue
            valor = obtener(resultado.columnas[subcedula])
            if valor != CERO:
                salida.append((casilla, nombre, valor))
    return sorted(salida)
