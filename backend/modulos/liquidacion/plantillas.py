"""Catálogo de deducciones y rentas exentas frecuentes.

Para qué
--------
Sin esto, el contador teclea «Intereses de vivienda / Art. 119 ET / sujeto al
límite» una vez por cada cliente. Con cien clientes son cien veces lo mismo,
y cada vez es una oportunidad de equivocarse en la clasificación frente al
límite del art. 336 num. 3, que es el error que más cambia el impuesto.

El catálogo trae el concepto, su norma, su tope propio en UVT cuando lo tiene
y si está sujeto al límite general. El contador sigue poniendo el valor: eso
depende de los soportes del contribuyente, no del catálogo.

Sobre `sujeto_a_limite_general`
-------------------------------
La clasificación sigue el texto del art. 336: el numeral 3 dice que la
deducción por dependientes va «en adición» al límite, y el numeral 5 dice
expresamente que el 1 % de compras «no está sujeta al límite» del numeral 3.
Parte de la doctrina divulgativa los clasifica como sujetos. Donde hay
discusión, la plantilla lo dice en `nota` para que el contador decida, que es
quien firma.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from .cedula_general import (
    DEDUCCION_OTRA,
    DEDUCCION_VIVIENDA,
    EXENTA_AFC,
    TRABAJO,
)


@dataclass(frozen=True)
class PlantillaDeduccion:
    codigo: str
    nombre: str
    fuente_legal: str
    sujeto_a_limite_general: bool
    tope_propio_uvt: Optional[Decimal] = None
    periodicidad_tope: str = "ANUAL"  # ANUAL | MENSUAL
    nota: str = ""
    # Fila del formulario 210. Los aportes a AFC, FVP y AVC y los intereses de
    # vivienda tienen casilla propia, separada del resto.
    fila: str = DEDUCCION_OTRA
    # Columna del formulario. `None` deja que el motor la reparta entre las
    # columnas con renta líquida; se fija solo cuando la norma la determina,
    # como en el art. 387, que exige relación laboral.
    subcedula_sugerida: Optional[str] = None


PLANTILLAS: List[PlantillaDeduccion] = [
    PlantillaDeduccion(
        codigo="INTERESES_VIVIENDA",
        fila=DEDUCCION_VIVIENDA,
        nombre="Intereses de crédito de vivienda",
        fuente_legal="Art. 119 ET",
        sujeto_a_limite_general=True,
        tope_propio_uvt=Decimal("1200"),
        nota="Solo los intereses, no el abono a capital. El crédito debe estar a "
             "nombre del contribuyente y sobre vivienda propia.",
    ),
    PlantillaDeduccion(
        codigo="INTERESES_ICETEX",
        nombre="Intereses de crédito Icetex para educación superior",
        fuente_legal="Art. 119 ET",
        sujeto_a_limite_general=True,
        tope_propio_uvt=Decimal("100"),
    ),
    PlantillaDeduccion(
        codigo="MEDICINA_PREPAGADA",
        fila=DEDUCCION_OTRA,
        subcedula_sugerida=TRABAJO,
        nombre="Medicina prepagada o póliza de salud",
        fuente_legal="Art. 387 num. 1 ET",
        sujeto_a_limite_general=True,
        tope_propio_uvt=Decimal("16"),
        periodicidad_tope="MENSUAL",
        nota="El tope es mensual: 16 UVT por mes. Debe estar a nombre del "
             "contribuyente y cubrir a él, su cónyuge o sus dependientes.",
    ),
    PlantillaDeduccion(
        codigo="DEPENDIENTES_387",
        fila=DEDUCCION_OTRA,
        subcedula_sugerida=TRABAJO,
        nombre="Dependientes económicos (art. 387)",
        fuente_legal="Art. 387 num. 2 ET",
        sujeto_a_limite_general=True,
        tope_propio_uvt=Decimal("32"),
        periodicidad_tope="MENSUAL",
        nota="10 % del ingreso bruto con tope de 32 UVT mensuales. Es distinta de "
             "la de 72 UVT por dependiente del art. 336 num. 3, que la aplicación "
             "calcula aparte: revise si en su caso se pueden tomar las dos.",
    ),
    PlantillaDeduccion(
        codigo="APORTES_VOLUNTARIOS_PENSION",
        fila=EXENTA_AFC,
        nombre="Aportes voluntarios a fondos de pensiones voluntarias",
        fuente_legal="Art. 126-1 ET",
        sujeto_a_limite_general=True,
        tope_propio_uvt=Decimal("3800"),
        nota="Junto con los aportes a AFC, el tope conjunto es del 30 % del ingreso "
             "laboral o tributario del año, sin exceder 3.800 UVT. Verifique el "
             "cálculo conjunto antes de solicitar los dos.",
    ),
    PlantillaDeduccion(
        codigo="AHORRO_AFC",
        fila=EXENTA_AFC,
        nombre="Ahorro en cuentas AFC o AVC",
        fuente_legal="Art. 126-4 ET",
        sujeto_a_limite_general=True,
        tope_propio_uvt=Decimal("3800"),
        nota="Comparte el tope del 30 % / 3.800 UVT con los aportes voluntarios a "
             "pensión. Retirar el dinero antes de los plazos de la norma obliga a "
             "reintegrar el beneficio.",
    ),
    PlantillaDeduccion(
        codigo="GMF",
        nombre="Gravamen a los movimientos financieros (4 × 1.000)",
        fuente_legal="Art. 115 ET",
        sujeto_a_limite_general=True,
        nota="Solo el 50 % del GMF efectivamente pagado, certificado por el banco. "
             "No requiere relación de causalidad con la renta.",
    ),
    PlantillaDeduccion(
        codigo="IMPUESTOS_PAGADOS",
        nombre="Impuestos pagados (predial, vehículos, ICA)",
        fuente_legal="Art. 115 ET",
        sujeto_a_limite_general=True,
        nota="Deben tener relación de causalidad con la actividad productora de "
             "renta y estar efectivamente pagados en el año. Verifique el "
             "tratamiento vigente del ICA, que ha cambiado con las últimas reformas.",
    ),
    PlantillaDeduccion(
        codigo="EXPENSAS_NECESARIAS",
        nombre="Expensas necesarias de la actividad",
        fuente_legal="Art. 107 ET",
        sujeto_a_limite_general=True,
        nota="Exige relación de causalidad, necesidad y proporcionalidad. Es la "
             "deducción que la DIAN más rechaza por falta de soporte.",
    ),
    PlantillaDeduccion(
        codigo="APORTES_SEGURIDAD_SOCIAL_EMPLEADA",
        nombre="Aportes a seguridad social de empleada o empleado del servicio doméstico",
        fuente_legal="Art. 387 ET",
        sujeto_a_limite_general=True,
        nota="Solo si el contribuyente figura como empleador y los aportes están "
             "efectivamente pagados.",
    ),
    PlantillaDeduccion(
        codigo="DEPENDIENTES_336",
        nombre="Dependientes (72 UVT c/u, art. 336)",
        fuente_legal="Art. 336 num. 3 ET",
        sujeto_a_limite_general=False,
        tope_propio_uvt=Decimal("288"),
        nota="La aplicación la calcula sola a partir del número de dependientes de "
             "la hoja: no la agregue aquí o quedará contada dos veces. Se deja en "
             "el catálogo solo como referencia.",
    ),
    PlantillaDeduccion(
        codigo="COMPRAS_1_PCT",
        nombre="1 % de compras con factura electrónica (art. 336 num. 5)",
        fuente_legal="Art. 336 num. 5 ET",
        sujeto_a_limite_general=False,
        tope_propio_uvt=Decimal("240"),
        nota="La aplicación la calcula sola a partir del valor de compras de la "
             "hoja: no la agregue aquí o quedará contada dos veces.",
    ),
]

# Conceptos que el motor ya calcula por su cuenta. Agregarlos como deducción
# manual los contaría dos veces, así que el servicio los rechaza.
CODIGOS_CALCULADOS_POR_EL_MOTOR = {"DEPENDIENTES_336", "COMPRAS_1_PCT"}

_POR_CODIGO = {p.codigo: p for p in PLANTILLAS}


def obtener(codigo: str) -> Optional[PlantillaDeduccion]:
    return _POR_CODIGO.get(codigo)


def catalogo(uvt: Decimal) -> List[dict]:
    """El catálogo con los topes ya convertidos a pesos del año consultado."""
    salida = []
    for p in PLANTILLAS:
        tope_pesos = None
        if p.tope_propio_uvt is not None:
            factor = Decimal(12) if p.periodicidad_tope == "MENSUAL" else Decimal(1)
            tope_pesos = p.tope_propio_uvt * uvt * factor
        salida.append(
            {
                "codigo": p.codigo,
                "nombre": p.nombre,
                "fuente_legal": p.fuente_legal,
                "sujeto_a_limite_general": p.sujeto_a_limite_general,
                "tope_propio_uvt": p.tope_propio_uvt,
                "periodicidad_tope": p.periodicidad_tope,
                "tope_anual_en_pesos": tope_pesos,
                "nota": p.nota,
                "lo_calcula_el_motor": p.codigo in CODIGOS_CALCULADOS_POR_EL_MOTOR,
                "fila": p.fila,
                "subcedula_sugerida": p.subcedula_sugerida,
            }
        )
    return salida
