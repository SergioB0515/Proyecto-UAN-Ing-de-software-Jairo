"""Parámetros tributarios oficiales, versionados por año gravable.

Por qué existe este archivo
---------------------------
El impuesto de renta de personas naturales cambia *todos los años*: la UVT se
reajusta por resolución de la DIAN cada diciembre, y los límites y tarifas
cambian con cada reforma. Si esos números quedan dispersos en el código, la
aplicación produce cifras equivocadas cada enero sin que nadie lo note.

Aquí viven en un solo lugar, agrupados por año gravable y **con la norma que
los fija citada al lado**. Para habilitar un año nuevo se agrega una entrada a
PARAMETROS_POR_ANIO; no se toca el motor de liquidación.

Convención de unidades
----------------------
- Todo importe en pesos es Decimal. Nunca float: en software contable el error
  de representación binaria de float se acumula y descuadra los totales.
- Los límites legales se expresan en UVT (como los escribe el Estatuto), no en
  pesos. El motor los convierte a pesos multiplicando por la UVT del año.

Estado de la normativa al 2026-11-03
------------------------------------
El régimen vigente para personas naturales es el de la Ley 2277 de 2022. El
proyecto de ley de financiamiento radicado en julio de 2026 fue archivado por
las comisiones económicas del Congreso, así que no modificó estos parámetros.
Si una reforma posterior se aprueba, se agrega un bloque nuevo con su propio
`regimen` y el motor sigue liquidando bien los años anteriores.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Estructuras
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TramoTarifa:
    """Un renglón de una tabla de tarifas marginales expresada en UVT.

    `impuesto_acumulado_uvt` es el impuesto de los tramos anteriores, tal como
    lo trae impreso la tabla del Estatuto. Guardarlo evita recalcularlo y
    permite comparar la implementación contra la tabla publicada renglón a
    renglón, que es lo que revisaría un contador.
    """

    desde_uvt: Decimal
    hasta_uvt: Optional[Decimal]  # None = sin límite superior
    tarifa_marginal: Decimal
    impuesto_acumulado_uvt: Decimal

    def contiene(self, base_uvt: Decimal) -> bool:
        if base_uvt <= self.desde_uvt:
            return False
        return self.hasta_uvt is None or base_uvt <= self.hasta_uvt


@dataclass(frozen=True)
class LimiteUvt:
    """Un límite legal con su porcentaje, su tope en UVT y su norma."""

    porcentaje: Optional[Decimal]
    tope_uvt: Optional[Decimal]
    fuente_legal: str


@dataclass(frozen=True)
class TopeDeduccion:
    """Tope propio de una deducción o renta exenta, aparte del límite general.

    `grupo` junta los conceptos que COMPARTEN un tope: los aportes voluntarios
    a pensión y el ahorro en AFC no tienen 3.800 UVT cada uno, tienen 3.800 UVT
    entre los dos. Tratarlos por separado duplicaría el beneficio.

    `porcentaje_de_ingresos` es un segundo techo que se evalúa junto con el
    tope en UVT: manda el menor de los dos.
    """

    codigo: str
    tope_uvt: Optional[Decimal]
    es_mensual: bool
    porcentaje_de_ingresos: Optional[Decimal]
    grupo: Optional[str]
    fuente_legal: str


@dataclass(frozen=True)
class LimiteBancarizacion:
    """Límites del art. 771-5 para aceptar pagos en efectivo.

    El límite general es el MENOR entre tres cifras, no una sola. El
    individual es un tope por operación, independiente del general.
    """

    porcentaje_de_pagos: Decimal
    tope_uvt: Decimal
    porcentaje_de_costos: Decimal
    limite_individual_uvt: Decimal
    fuente_legal: str


@dataclass(frozen=True)
class ParametrosAnuales:
    anio_gravable: int
    regimen: str
    uvt: Decimal
    fuente_uvt: str

    # Tarifa del impuesto sobre la renta de personas naturales residentes.
    tabla_renta: Tuple[TramoTarifa, ...]
    fuente_tabla_renta: str

    # Depuración de la cédula general.
    limite_general: LimiteUvt            # art. 336 num. 3
    deduccion_dependientes: LimiteUvt    # art. 336 num. 3, inciso
    max_dependientes: int
    deduccion_compras: LimiteUvt         # art. 336 num. 5
    renta_exenta_trabajo: LimiteUvt      # art. 206 num. 10
    renta_exenta_pensiones_uvt_mensual: Decimal  # art. 206 num. 5
    fuente_renta_exenta_pensiones: str

    # Dividendos (residentes).
    descuento_dividendos: LimiteUvt      # art. 254-1
    # Tarifa general del art. 240 que el art. 242 inc. 2 aplica a los dividendos
    # gravados (par. 2 del art. 49) antes de llevarlos a la tabla del art. 241.
    tarifa_dividendos_gravados: Decimal
    fuente_dividendos_gravados: str

    # Ganancias ocasionales.
    tarifa_ganancia_ocasional: Decimal
    tarifa_ganancia_ocasional_loterias: Decimal
    fuente_ganancia_ocasional: str
    exencion_go_vivienda_uvt: Decimal

    # Topes propios de cada deducción, anteriores al límite general.
    topes_deducciones: Dict[str, TopeDeduccion]

    # Pagos en efectivo (bancarización).
    bancarizacion: LimiteBancarizacion

    # Depreciación: tasa anual máxima por tipo de bien (art. 137).
    tasas_depreciacion: Dict[str, Decimal]
    fuente_depreciacion: str

    # Compensación de pérdidas fiscales.
    anios_compensacion_perdidas: int
    fuente_compensacion_perdidas: str

    # Renta presuntiva.
    tarifa_renta_presuntiva: Decimal
    fuente_renta_presuntiva: str

    # Anticipo del año siguiente (art. 807).
    anticipo_primer_anio: Decimal
    anticipo_segundo_anio: Decimal
    anticipo_siguientes: Decimal
    fuente_anticipo: str

    # Topes que obligan a declarar.
    topes_declarar_uvt: Dict[str, Decimal] = field(default_factory=dict)
    fuente_topes_declarar: str = ""

    # Notas que el motor arrastra hasta la respuesta de la API, para que el
    # contador vea dónde la norma es interpretable y no confíe a ciegas.
    notas: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Tabla del artículo 241 ET (vigente: Ley 2010 de 2019, art. 34)
#
# Rango UVT              Marginal   Impuesto
# > 0      a  1.090        0%       0
# > 1.090  a  1.700       19%       19% del exceso sobre 1.090
# > 1.700  a  4.100       28%       116 UVT + 28% del exceso sobre 1.700
# > 4.100  a  8.670       33%       788 UVT + 33% del exceso sobre 4.100
# > 8.670  a 18.970       35%       2.296 UVT + 35% del exceso sobre 8.670
# > 18.970 a 31.000       37%       5.901 UVT + 37% del exceso sobre 18.970
# > 31.000                39%       10.352 UVT + 39% del exceso sobre 31.000
# ---------------------------------------------------------------------------

_TABLA_241 = (
    TramoTarifa(Decimal("0"), Decimal("1090"), Decimal("0.00"), Decimal("0")),
    TramoTarifa(Decimal("1090"), Decimal("1700"), Decimal("0.19"), Decimal("0")),
    TramoTarifa(Decimal("1700"), Decimal("4100"), Decimal("0.28"), Decimal("116")),
    TramoTarifa(Decimal("4100"), Decimal("8670"), Decimal("0.33"), Decimal("788")),
    TramoTarifa(Decimal("8670"), Decimal("18970"), Decimal("0.35"), Decimal("2296")),
    TramoTarifa(Decimal("18970"), Decimal("31000"), Decimal("0.37"), Decimal("5901")),
    TramoTarifa(Decimal("31000"), None, Decimal("0.39"), Decimal("10352")),
)

# ---------------------------------------------------------------------------
# Tasas máximas de depreciación anual (art. 137 ET)
#
# La norma fija topes de tasa anual, no vidas útiles mínimas: el contribuyente
# puede estimar una vida útil menor, pero solo deduce hasta esta tasa. Por eso
# el motor calcula la depreciación con la vida útil que registre el contador y
# la recorta a este tope, en vez de imponer la vida útil.
# ---------------------------------------------------------------------------

_TASAS_DEPRECIACION = {
    "CONSTRUCCIONES_Y_EDIFICACIONES": Decimal("0.0222"),
    "ACUEDUCTO_PLANTA_Y_REDES": Decimal("0.0250"),
    "VIAS_DE_COMUNICACION": Decimal("0.0250"),
    "FLOTA_Y_EQUIPO_AEREO": Decimal("0.0333"),
    "FLOTA_Y_EQUIPO_FERREO": Decimal("0.0500"),
    "FLOTA_Y_EQUIPO_FLUVIAL": Decimal("0.0667"),
    "ARMAMENTO_Y_EQUIPO_DE_VIGILANCIA": Decimal("0.1000"),
    "EQUIPO_ELECTRICO": Decimal("0.1000"),
    "FLOTA_Y_EQUIPO_DE_TRANSPORTE_TERRESTRE": Decimal("0.1000"),
    "MAQUINARIA_Y_EQUIPOS": Decimal("0.1000"),
    "MUEBLES_Y_ENSERES": Decimal("0.1000"),
    "EQUIPO_MEDICO_CIENTIFICO": Decimal("0.1250"),
    "ENVASES_EMPAQUES_Y_HERRAMIENTAS": Decimal("0.2000"),
    "EQUIPO_DE_COMPUTACION": Decimal("0.2000"),
    "REDES_DE_PROCESAMIENTO_DE_DATOS": Decimal("0.2000"),
    "EQUIPO_DE_COMUNICACION": Decimal("0.2000"),
}

# ---------------------------------------------------------------------------
# Topes propios de las deducciones y rentas exentas
#
# Se aplican ANTES del límite general del art. 336 num. 3: primero cada
# concepto se recorta a su propio techo, y solo después la suma pasa por el
# 40 % / 1.340 UVT. Invertir el orden acepta deducciones improcedentes cuando
# el límite general no alcanza a morder.
#
# Los cuatro están en el instructivo oficial del formulario 210 de la DIAN.
# ---------------------------------------------------------------------------

_TOPES_DEDUCCIONES = {
    "INTERESES_VIVIENDA": TopeDeduccion(
        "INTERESES_VIVIENDA", Decimal("1200"), False, None, None,
        "Art. 119 ET (1.200 UVT anuales)",
    ),
    "INTERESES_ICETEX": TopeDeduccion(
        "INTERESES_ICETEX", Decimal("100"), False, None, None,
        "Art. 119 ET (100 UVT anuales)",
    ),
    "MEDICINA_PREPAGADA": TopeDeduccion(
        "MEDICINA_PREPAGADA", Decimal("16"), True, None, None,
        "Art. 387 num. 1 ET (16 UVT mensuales)",
    ),
    "DEPENDIENTES_387": TopeDeduccion(
        "DEPENDIENTES_387", Decimal("32"), True, Decimal("0.10"), None,
        "Art. 387 num. 2 ET (10 % del ingreso, tope 32 UVT mensuales)",
    ),
    "APORTES_VOLUNTARIOS_PENSION": TopeDeduccion(
        "APORTES_VOLUNTARIOS_PENSION", Decimal("3800"), False, Decimal("0.30"),
        "AHORRO_PREVISIONAL",
        "Art. 126-1 ET (30 % del ingreso, tope 3.800 UVT, compartido con AFC)",
    ),
    "AHORRO_AFC": TopeDeduccion(
        "AHORRO_AFC", Decimal("3800"), False, Decimal("0.30"), "AHORRO_PREVISIONAL",
        "Art. 126-4 ET (30 % del ingreso, tope 3.800 UVT, compartido con pensión voluntaria)",
    ),
}

_TOPES_DECLARAR = {
    "patrimonio_bruto": Decimal("4500"),
    "ingresos_brutos": Decimal("1400"),
    "consumos_tarjeta_credito": Decimal("1400"),
    "compras_y_consumos": Decimal("1400"),
    "consignaciones_y_depositos": Decimal("1400"),
}

_NOTAS_LEY_2277 = (
    "Los dividendos de residentes no tienen tabla propia desde el año gravable "
    "2023: entran a la base del art. 241 y generan el descuento del art. 254-1. "
    "La ubicación exacta en los renglones del formulario 210 la define la "
    "resolución de la DIAN que prescribe el formulario de cada año; verifícala "
    "antes de transcribir.",
    "El tope de ingresos brutos del art. 592 está redactado como «inferiores a "
    "1.400 UVT», mientras los demás topes dicen «no excedan». Un valor exactamente "
    "igual al tope obliga a declarar en ingresos, pero no en los otros criterios.",
    "Esta liquidación no evalúa la condición de responsable de IVA al 31 de "
    "diciembre, que también obliga a declarar y no aparece en la exógena.",
)


def _parametros_ley_2277(anio: int, uvt: str, fuente_uvt: str) -> ParametrosAnuales:
    """Construye los parámetros de un año bajo el régimen de la Ley 2277 de 2022.

    Solo cambia la UVT entre 2023 y 2026; el resto de los límites se fijan en
    UVT y no se reajustan. Factorizarlo así evita que una corrección se aplique
    a un año y se olvide en otro.
    """
    return ParametrosAnuales(
        anio_gravable=anio,
        regimen="LEY_2277_2022",
        uvt=Decimal(uvt),
        fuente_uvt=fuente_uvt,
        tabla_renta=_TABLA_241,
        fuente_tabla_renta="Art. 241 ET, modificado por la Ley 2010 de 2019, art. 34",
        limite_general=LimiteUvt(
            porcentaje=Decimal("0.40"),
            tope_uvt=Decimal("1340"),
            fuente_legal="Art. 336 num. 3 ET, modificado por la Ley 2277 de 2022, art. 7",
        ),
        deduccion_dependientes=LimiteUvt(
            porcentaje=None,
            tope_uvt=Decimal("72"),
            fuente_legal="Art. 336 num. 3 ET (deducción por dependiente, adicional al límite general)",
        ),
        max_dependientes=4,
        deduccion_compras=LimiteUvt(
            porcentaje=Decimal("0.01"),
            tope_uvt=Decimal("240"),
            fuente_legal="Art. 336 num. 5 ET (no sujeta al límite del num. 3)",
        ),
        renta_exenta_trabajo=LimiteUvt(
            porcentaje=Decimal("0.25"),
            tope_uvt=Decimal("790"),
            fuente_legal="Art. 206 num. 10 ET",
        ),
        renta_exenta_pensiones_uvt_mensual=Decimal("1000"),
        fuente_renta_exenta_pensiones="Art. 206 num. 5 ET (1.000 UVT mensuales)",
        descuento_dividendos=LimiteUvt(
            porcentaje=Decimal("0.19"),
            tope_uvt=Decimal("1090"),  # umbral: el descuento aplica sobre el exceso
            fuente_legal="Art. 254-1 ET, adicionado por la Ley 2277 de 2022, art. 12",
        ),
        tarifa_dividendos_gravados=Decimal("0.35"),
        fuente_dividendos_gravados=(
            "Art. 242 inc. 2 ET y art. 240 ET (tarifa general del 35 % desde el "
            "año gravable 2023); instructivo del formulario 210, casillas 111 y 118"
        ),
        tarifa_ganancia_ocasional=Decimal("0.15"),
        tarifa_ganancia_ocasional_loterias=Decimal("0.20"),
        fuente_ganancia_ocasional="Arts. 313 a 317 ET, modificados por la Ley 2277 de 2022, arts. 32 a 35",
        exencion_go_vivienda_uvt=Decimal("5000"),
        topes_deducciones=dict(_TOPES_DEDUCCIONES),
        bancarizacion=LimiteBancarizacion(
            porcentaje_de_pagos=Decimal("0.40"),
            tope_uvt=Decimal("40000"),
            porcentaje_de_costos=Decimal("0.35"),
            limite_individual_uvt=Decimal("100"),
            fuente_legal="Art. 771-5 ET, parágrafos 1 y 2 (límites definitivos desde 2021)",
        ),
        tasas_depreciacion=dict(_TASAS_DEPRECIACION),
        fuente_depreciacion="Art. 137 ET (tasas anuales máximas); arts. 128 a 131 ET",
        anios_compensacion_perdidas=12,
        fuente_compensacion_perdidas=(
            "Art. 147 ET por remisión del art. 1.2.1.20.6 del DUR 1625 de 2016; "
            "art. 330 ET: solo contra rentas del mismo tipo"
        ),
        tarifa_renta_presuntiva=Decimal("0.00"),
        fuente_renta_presuntiva="Art. 188 ET: 0 % desde el año gravable 2021 (Ley 2010 de 2019, art. 78)",
        anticipo_primer_anio=Decimal("0.25"),
        anticipo_segundo_anio=Decimal("0.50"),
        anticipo_siguientes=Decimal("0.75"),
        fuente_anticipo="Art. 807 ET",
        topes_declarar_uvt=dict(_TOPES_DECLARAR),
        fuente_topes_declarar="Arts. 592 y 594-3 ET; art. 1.6.1.13.2.7 del DUR 1625 de 2016",
        notas=_NOTAS_LEY_2277,
    )


PARAMETROS_POR_ANIO: Dict[int, ParametrosAnuales] = {
    2023: _parametros_ley_2277(
        2023, "42412", "Resolución DIAN 001264 del 18 de noviembre de 2022"
    ),
    2024: _parametros_ley_2277(
        2024, "47065", "Resolución DIAN 000187 del 28 de noviembre de 2023"
    ),
    2025: _parametros_ley_2277(
        2025, "49799", "Resolución DIAN que fijó la UVT de 2025 (verificar número)"
    ),
    2026: _parametros_ley_2277(
        2026, "52374", "Resolución DIAN 000238 del 15 de diciembre de 2025"
    ),
}

ANIOS_SOPORTADOS: List[int] = sorted(PARAMETROS_POR_ANIO)
