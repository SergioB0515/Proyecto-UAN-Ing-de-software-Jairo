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
- Casillas 29 a 76: transcritas del PDF oficial del formulario 210 publicado
  por la DIAN para el año gravable 2024.
- Casillas 91 a 137: tomadas de una guía especializada, no del PDF oficial (la
  extracción del PDF se corta en la casilla 76). Marcadas `verificado=False`:
  hay que confirmarlas contra el instructivo oficial antes de imprimirlas en un
  documento que alguien vaya a transcribir.
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


_OFICIAL_2024 = "Formulario 210 AG 2024 publicado por la DIAN (PDF oficial)"
_SECUNDARIA = "Guía especializada — PENDIENTE de confirmar contra el instructivo oficial"


def _c(numero: int, nombre: str, verificado: bool = True) -> CasillaOficial:
    return CasillaOficial(
        numero=numero,
        nombre=nombre,
        verificado=verificado,
        fuente=_OFICIAL_2024 if verificado else _SECUNDARIA,
    )


# Casillas del formulario, por número. Es el catálogo de referencia completo:
# sirve para mostrarle al contador el nombre oficial de cada casilla aunque el
# motor todavía no produzca el valor de todas.
CASILLAS_2024: Dict[int, CasillaOficial] = {
    # Patrimonio
    29: _c(29, "Total patrimonio bruto"),
    30: _c(30, "Deudas"),
    31: _c(31, "Total patrimonio líquido"),
    # Cédula general — rentas de trabajo
    32: _c(32, "Ingresos brutos de las rentas de trabajo"),
    33: _c(33, "Ingresos no constitutivos de renta de las rentas de trabajo"),
    34: _c(34, "Renta líquida de las rentas de trabajo"),
    35: _c(35, "Rentas exentas — aportes voluntarios AFC, FVP y/o AVC"),
    36: _c(36, "Rentas exentas — otras rentas exentas"),
    37: _c(37, "Total rentas exentas de las rentas de trabajo"),
    38: _c(38, "Deducciones imputables — intereses de vivienda"),
    39: _c(39, "Deducciones imputables — otras deducciones imputables"),
    40: _c(40, "Total deducciones imputables a las rentas de trabajo"),
    41: _c(41, "Rentas exentas y/o deducciones imputables a las rentas de trabajo (limitadas)"),
    42: _c(42, "Renta líquida ordinaria de las rentas de trabajo"),
    # Rentas de trabajo sin relación laboral
    43: _c(43, "Ingresos brutos de las rentas de trabajo sin relación laboral"),
    44: _c(44, "Ingresos no constitutivos de renta — sin relación laboral"),
    45: _c(45, "Costos y deducciones procedentes — sin relación laboral"),
    46: _c(46, "Renta líquida de las rentas de trabajo sin relación laboral"),
    49: _c(49, "Total rentas exentas — sin relación laboral"),
    52: _c(52, "Total deducciones imputables — sin relación laboral"),
    53: _c(53, "Rentas exentas y/o deducciones imputables (limitadas) — sin relación laboral"),
    54: _c(54, "Renta líquida ordinaria del ejercicio — sin relación laboral"),
    55: _c(55, "Pérdida líquida ordinaria del ejercicio — sin relación laboral"),
    56: _c(56, "Compensaciones por pérdidas — sin relación laboral"),
    57: _c(57, "Renta líquida ordinaria — sin relación laboral"),
    # Rentas de capital
    58: _c(58, "Ingresos brutos de las rentas de capital"),
    59: _c(59, "Ingresos no constitutivos de renta de las rentas de capital"),
    60: _c(60, "Costos y deducciones procedentes de las rentas de capital"),
    61: _c(61, "Renta líquida de las rentas de capital"),
    62: _c(62, "Rentas líquidas pasivas — ECE de las rentas de capital"),
    65: _c(65, "Total rentas exentas de las rentas de capital"),
    68: _c(68, "Total deducciones imputables a las rentas de capital"),
    69: _c(69, "Rentas exentas y/o deducciones imputables a las rentas de capital (limitadas)"),
    70: _c(70, "Renta líquida ordinaria del ejercicio de las rentas de capital"),
    71: _c(71, "Pérdida líquida del ejercicio de las rentas de capital"),
    72: _c(72, "Compensaciones por pérdidas de las rentas de capital"),
    73: _c(73, "Renta líquida ordinaria de las rentas de capital"),
    # Rentas no laborales
    74: _c(74, "Ingresos brutos de las rentas no laborales"),
    75: _c(75, "Devoluciones, rebajas y descuentos de las rentas no laborales"),
    76: _c(76, "Ingresos no constitutivos de renta de las rentas no laborales"),
    # Cierre de la cédula general y siguientes (pendientes de confirmar)
    91: _c(91, "Renta líquida bruta de la cédula general", False),
    93: _c(93, "Renta líquida ordinaria de la cédula general", False),
    97: _c(97, "Renta líquida gravable de la cédula general", False),
    98: _c(98, "Renta presuntiva", False),
    103: _c(103, "Renta líquida gravable de pensiones", False),
    107: _c(107, "Dividendos y participaciones — primera subcédula", False),
    108: _c(108, "Dividendos y participaciones — segunda subcédula", False),
    111: _c(111, "Base gravable conjunta del art. 241", False),
    115: _c(115, "Ganancias ocasionales gravables", False),
    116: _c(116, "Impuesto del art. 241 (renta ordinaria mayor que la presuntiva)", False),
    121: _c(121, "Total impuesto sobre las rentas líquidas gravables", False),
    125: _c(125, "Total descuentos tributarios", False),
    126: _c(126, "Impuesto neto de renta", False),
    127: _c(127, "Impuesto de ganancias ocasionales", False),
    129: _c(129, "Total impuesto a cargo", False),
    130: _c(130, "Anticipo liquidado en la declaración del año anterior", False),
    131: _c(131, "Saldo a favor del año anterior sin devolución ni compensación", False),
    132: _c(132, "Total retenciones en la fuente del año gravable", False),
    133: _c(133, "Anticipo para el año gravable siguiente", False),
    136: _c(136, "Total saldo a pagar", False),
    137: _c(137, "Total saldo a favor", False),
}

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
