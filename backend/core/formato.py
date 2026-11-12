"""Formato de cifras para los mensajes que lee el contador."""

from decimal import ROUND_HALF_UP, Decimal


def pesos(valor) -> str:
    """Pesos colombianos sin decimales y con punto de miles: «$1.234.567».

    Python separa los miles con coma; en Colombia la coma es el separador
    decimal, y un mensaje con «$1,234,567» se lee como otra cifra.
    """
    entero = Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    signo = "-" if entero < 0 else ""
    return f"{signo}${abs(int(entero)):,}".replace(",", ".")
