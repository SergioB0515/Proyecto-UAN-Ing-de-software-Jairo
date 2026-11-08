"""Numeración oficial de los renglones del formulario 210.

Por qué existe
-------------
El motor produce los valores con códigos propios (`CG-INGRESOS`,
`SALDO-A-PAGAR`). Para que el contador pueda digitar el borrador en MUISCA sin
traducir nada, el archivo exportado tiene que traer el **número de casilla
oficial** al lado de cada cifra.

La numeración la fija la resolución de la DIAN que prescribe el formulario de
cada año gravable y puede cambiar de un año a otro, así que vive aquí, por año,
igual que los parámetros tributarios.

Estado de la verificación
-------------------------
- Todas las casillas se transcribieron del formulario 210 del año gravable
  2024 y de su instructivo, publicados por la DIAN.
- Año gravable 2025: **no verificado**. Mientras no se confirme la resolución
  del 210 de 2025, se usa la numeración de 2024 y el exportado lo advierte.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class CasillaOficial:
    numero: int
    nombre: str
    verificado: bool
    fuente: str


_OFICIAL_2024 = "Formulario 210 AG 2024 e instructivo, publicados por la DIAN"


def _c(numero: int, nombre: str, verificado: bool = True) -> CasillaOficial:
    return CasillaOficial(numero=numero, nombre=nombre, verificado=verificado,
                          fuente=_OFICIAL_2024)


# La cédula general es una grilla: las mismas filas conceptuales repetidas en
# cuatro columnas, una por subcédula. Se declara así, como grilla, porque es
# como está impresa en el formulario y porque deja ver de un vistazo qué
# conceptos NO existen en una subcédula (las rentas de trabajo con vínculo
# laboral no admiten costos, así que esa celda no tiene casilla).
#
# Orden de las columnas: trabajo · trabajo sin vínculo · capital · no laborales
_GRILLA_CEDULA_GENERAL = {
    "Ingresos brutos": (32, 43, 58, 74),
    "Devoluciones, rebajas y descuentos": (None, None, None, 75),
    "Ingresos no constitutivos de renta": (33, 44, 59, 76),
    "Costos y deducciones procedentes": (None, 45, 60, 77),
    "Renta líquida": (34, 46, 61, 78),
    "Rentas líquidas pasivas — ECE": (None, None, 62, 79),
    "Rentas exentas — aportes voluntarios AFC, FVP y AVC": (35, 47, 63, 80),
    "Rentas exentas — otras rentas exentas": (36, 48, 64, 81),
    "Total rentas exentas": (37, 49, 65, 82),
    "Deducciones imputables — intereses de vivienda": (38, 50, 66, 83),
    "Deducciones imputables — otras deducciones imputables": (39, 51, 67, 84),
    "Total deducciones imputables": (40, 52, 68, 85),
    "Rentas exentas y/o deducciones imputables (limitadas)": (41, 53, 69, 86),
    "Renta líquida ordinaria del ejercicio": (None, 54, 70, 87),
    "Pérdida líquida del ejercicio": (None, 55, 71, 88),
    "Compensaciones por pérdidas": (None, 56, 72, 89),
    "Renta líquida ordinaria": (42, 57, 73, 90),
}

SUBCEDULAS = ("TRABAJO", "TRABAJO_SIN_VINCULO", "CAPITAL", "NO_LABORAL")

_ETIQUETA_SUBCEDULA = {
    "TRABAJO": "rentas de trabajo",
    "TRABAJO_SIN_VINCULO": "rentas de trabajo sin relación laboral",
    "CAPITAL": "rentas de capital",
    "NO_LABORAL": "rentas no laborales",
}

_RESTO = {
    91: "Renta líquida cédula general",
    92: "Rentas exentas y deducciones imputables (limitadas) de la cédula general",
    93: "Renta líquida ordinaria de la cédula general",
    94: "Compensación por pérdidas de años gravables 2018 y anteriores",
    95: "Compensación por exceso de renta presuntiva",
    96: "Rentas gravables",
    97: "Renta líquida gravable de la cédula general",
    98: "Renta presuntiva",
    99: "Ingresos brutos por rentas de pensiones del país y del exterior",
    100: "Ingresos no constitutivos de renta de la cédula de pensiones",
    101: "Renta líquida de la cédula de pensiones",
    102: "Rentas exentas de pensiones",
    103: "Renta líquida gravable de la cédula de pensiones",
    104: "Dividendos y participaciones 2016 y anteriores, y otros",
    105: "Ingresos no constitutivos de renta de la cédula de dividendos",
    106: "Renta líquida ordinaria año 2016 y anteriores",
    107: "1a subcédula años 2017 y siguientes, numeral 3 art. 49 ET",
    108: "2a subcédula años 2017 y siguientes, parágrafo 2 art. 49 ET",
    109: "Dividendos y participaciones recibidos del exterior",
    110: "Rentas exentas de la casilla 109",
    111: "Renta líquida gravable (cédula general o renta presuntiva, de pensiones y de dividendos, art. 241 ET)",
    112: "Ingresos por ganancias ocasionales del país y del exterior",
    113: "Costos por ganancias ocasionales",
    114: "Ganancias ocasionales no gravadas y exentas",
    115: "Ganancias ocasionales gravables",
    116: "Impuesto sobre las rentas líquidas gravables — cédula general y de pensiones",
    117: "Impuesto sobre las rentas líquidas gravables — renta presuntiva",
    118: "Impuesto por dividendos y participaciones 2017 y siguientes, 2a subcédula (art. 240 ET)",
    119: "Impuesto por dividendos y participaciones año 2016",
    120: "Impuesto por dividendos y participaciones recibidos del exterior",
    121: "Total impuesto sobre las rentas líquidas gravables",
    122: "Descuento por impuestos pagados en el exterior",
    123: "Descuento por donaciones",
    124: "Descuento por dividendos, participaciones y otros",
    125: "Total descuentos tributarios",
    126: "Impuesto neto de renta",
    127: "Impuesto de ganancias ocasionales",
    128: "Descuento por impuestos pagados en el exterior por ganancias ocasionales",
    129: "Total impuesto a cargo",
    130: "Anticipo de renta liquidado en el año gravable anterior",
    131: "Saldo a favor del año gravable anterior sin solicitud de devolución o compensación",
    132: "Retenciones del año gravable a declarar",
    133: "Anticipo de renta para el año gravable siguiente",
    134: "Saldo a pagar por impuesto",
    135: "Sanciones",
    136: "Total saldo a pagar",
    137: "Total saldo a favor",
    138: "Número de dependientes económicos",
    139: "Adición por dependientes a la casilla 92",
    140: "Superó el tope indicativo del art. 336-1 ET",
    141: "Aporte voluntario",
    29: "Total patrimonio bruto",
    30: "Deudas",
    31: "Total patrimonio líquido",
    28: "Uno por ciento (1 %) de compras con factura electrónica",
}

CASILLAS_2024: Dict[int, CasillaOficial] = {n: _c(n, nombre) for n, nombre in _RESTO.items()}
for _fila, _numeros in _GRILLA_CEDULA_GENERAL.items():
    for _sub, _num in zip(SUBCEDULAS, _numeros):
        if _num is not None:
            CASILLAS_2024[_num] = _c(_num, f"{_fila} — {_ETIQUETA_SUBCEDULA[_sub]}")


def casilla_de_subcedula(fila: str, subcedula: str) -> Optional[int]:
    """Número de casilla de una fila de la grilla en una subcédula concreta.

    Devuelve None cuando esa combinación no existe en el formulario, que es
    información y no un error: las rentas de trabajo con vínculo laboral no
    tienen casilla de costos porque la ley no permite restarlos.
    """
    numeros = _GRILLA_CEDULA_GENERAL.get(fila)
    if numeros is None or subcedula not in SUBCEDULAS:
        return None
    return numeros[SUBCEDULAS.index(subcedula)]


# Código del motor → casilla oficial.
#
# Solo figuran los códigos que corresponden a UNA casilla del formulario. Varios
# renglones del motor son agregados de la cédula general y el formulario los pide
# separados por subcédula (ingresos de trabajo en la 32, de capital en la 58, no
# laborales en la 74...). Esos no se pueden mapear hasta que el motor emita el
# detalle por subcédula; están listados en SIN_MAPEO_POR_AGREGACION.
MAPEO_2024: Dict[str, int] = {
    "PAT-BRUTO": 29,
    "PAT-DEUDAS": 30,
    "PAT-LIQUIDO": 31,
    "RENTA-PRESUNTIVA": 98,
    "PEN-RENTA-LIQUIDA": 103,
    "DIV-RENTA-LIQUIDA": 107,
    "BASE-GRAVABLE": 111,
    "GO-BASE": 115,
    "IMP-RENTA": 116,
    "TOTAL-DESCUENTOS": 125,
    "IMP-NETO": 126,
    "GO-IMPUESTO": 127,
    "TOTAL-A-CARGO": 129,
    "RETENCIONES": 132,
    "ANTICIPO-SIGUIENTE": 133,
    "SALDO-A-PAGAR": 136,
    "SALDO-A-FAVOR": 137,
}

SIN_MAPEO_POR_AGREGACION = {
    "CG-INGRESOS": "El formulario separa los ingresos por subcédula: 32 (trabajo), 43 (sin relación laboral), 58 (capital), 74 (no laborales).",
    "CG-INCRNGO": "Separados en 33, 44, 59 y 76.",
    "CG-COSTOS": "Separados en 45 (sin relación laboral), 60 (capital) y los de no laborales.",
    "CG-EXENTAS-LIMITADAS": "Separadas en 41, 53 y 69, una por subcédula.",
    "CG-COMPENSACION": "Separada en 56 (sin relación laboral) y 72 (capital).",
    "CG-RENTA-LIQUIDA": "El formulario la arma por subcédula (42, 57, 73) y la consolida en 93 y 97.",
}

# La numeración de 2025 no se ha confirmado contra la resolución del año.
# Reutilizarla sin decirlo produciría un documento que parece oficial y no lo es.
MAPEO_POR_ANIO: Dict[int, Dict[str, int]] = {2024: MAPEO_2024}
CASILLAS_POR_ANIO: Dict[int, Dict[int, CasillaOficial]] = {2024: CASILLAS_2024}

ADVERTENCIA_ANIO_NO_VERIFICADO = (
    "La numeración de casillas mostrada es la del formulario 210 del año "
    "gravable 2024. La DIAN puede renumerar el formulario cada año: confirme "
    "los números contra la resolución que prescribe el formulario del año que "
    "está declarando antes de transcribir."
)


def casilla_de(codigo_motor: str, anio_gravable: int) -> Optional[CasillaOficial]:
    """Casilla oficial de un renglón del motor, o None si no hay mapeo directo."""
    mapeo = MAPEO_POR_ANIO.get(anio_gravable) or MAPEO_2024
    casillas = CASILLAS_POR_ANIO.get(anio_gravable) or CASILLAS_2024
    numero = mapeo.get(codigo_motor)
    return casillas.get(numero) if numero else None


def casilla_por_numero(numero: Optional[int], anio_gravable: int) -> Optional[CasillaOficial]:
    """Casilla por su número, para traducir los «R29» que trae la exógena.

    El archivo de la DIAN ya dice a qué renglón va cada valor con esta misma
    numeración, así que traducir el código al nombre oficial no requiere
    ninguna inferencia: solo mirar el catálogo.
    """
    if numero is None:
        return None
    casillas = CASILLAS_POR_ANIO.get(anio_gravable) or CASILLAS_2024
    return casillas.get(numero)
