"""Sugiere la cédula de una fuente de ingreso por palabras del concepto.

Solo sugiere; el motor liquida lo confirmado por el contador.
Pendiente: clasificar por código de concepto de la exógena.
"""

from typing import Dict, List, Tuple

from .modelos import Cedula

# Gana la primera coincidencia: lo específico primero ("pensión" antes que "pago").
_REGLAS: Tuple[Tuple[Cedula, Tuple[str, ...]], ...] = (
    (
        Cedula.EXCLUIDO,
        ("pension", "pensión", "mesada", "dividendo", "participacion", "participación",
         "ganancia ocasional", "herencia", "loteria", "lotería", "rifa", "premio"),
    ),
    (
        Cedula.TRABAJO,
        ("salario", "sueldo", "nomina", "nómina", "laboral", "prima", "cesantia",
         "cesantía", "vacacion", "vacación", "bonificacion", "bonificación",
         "indemnizacion laboral", "empleador"),
    ),
    (
        Cedula.TRABAJO_SIN_VINCULO,
        ("honorario", "comision", "comisión", "servicio personal", "prestacion de servicios",
         "prestación de servicios", "contrato de obra"),
    ),
    (
        Cedula.CAPITAL,
        ("interes", "interés", "rendimiento", "arrendamiento", "arriendo", "canon",
         "regalia", "regalía", "propiedad intelectual", "cdt", "cuenta de ahorro"),
    ),
    (
        Cedula.NO_LABORAL,
        ("venta", "mercancia", "mercancía", "comercial", "enajenacion", "enajenación",
         "indemnizacion", "indemnización", "subsidio", "aporte", "otros ingresos"),
    ),
)

_EXPLICACIONES: Dict[Cedula, str] = {
    Cedula.TRABAJO: "Rentas de trabajo con vínculo laboral (art. 335 ET): admiten la renta exenta del 25 % del art. 206 num. 10 y no admiten costos ni gastos.",
    Cedula.TRABAJO_SIN_VINCULO: "Rentas de trabajo sin vínculo laboral (honorarios y compensaciones): hay que elegir entre restar costos y gastos o tomar la renta exenta del 25 % (art. 336 num. 4).",
    Cedula.CAPITAL: "Rentas de capital (art. 338 ET): intereses, arrendamientos y regalías; admiten costos y gastos imputables.",
    Cedula.NO_LABORAL: "Rentas no laborales (art. 340 ET): todo lo que no encaja en las anteriores; admiten costos y gastos imputables.",
    Cedula.EXCLUIDO: "No pertenece a la cédula general: va en la cédula de pensiones, en dividendos o en ganancias ocasionales, que se capturan en la hoja de liquidación.",
    Cedula.SIN_CLASIFICAR: "No se pudo sugerir una cédula. Clasifíquelo a mano: el motor lo excluye del cálculo mientras siga así.",
}


def sugerir_cedula(concepto: str) -> Cedula:
    texto = (concepto or "").lower()
    for cedula, palabras in _REGLAS:
        if any(palabra in texto for palabra in palabras):
            return cedula
    return Cedula.SIN_CLASIFICAR


def explicar(cedula: Cedula) -> str:
    return _EXPLICACIONES.get(cedula, "")


def cedulas_disponibles() -> List[Dict[str, str]]:
    """Catálogo de cédulas para el frontend."""
    etiquetas = {
        Cedula.TRABAJO: "Rentas de trabajo (con vínculo laboral)",
        Cedula.TRABAJO_SIN_VINCULO: "Rentas de trabajo sin vínculo laboral",
        Cedula.CAPITAL: "Rentas de capital",
        Cedula.NO_LABORAL: "Rentas no laborales",
        Cedula.EXCLUIDO: "Fuera de la cédula general",
        Cedula.SIN_CLASIFICAR: "Sin clasificar",
    }
    return [
        {"valor": c.value, "etiqueta": etiquetas[c], "implicacion": explicar(c)}
        for c in Cedula
    ]
