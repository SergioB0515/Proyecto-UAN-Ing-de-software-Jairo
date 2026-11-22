"""Tipos y ayudas para las cifras del dominio: dinero y cantidades.

Por qué no `float`
------------------
`float` no representa exactamente los valores decimales que usa la
contabilidad: `0.1 + 0.2` da `0.30000000000000004`. El error es diminuto y se
acumula sumando renglones, así que los totales dejan de cuadrar al centavo.
Un contador que ve un descuadre de $0,03 en un informe deja de confiar en todo
lo demás, y tiene razón: si eso está mal, no sabe qué más está mal.

`Decimal` sobre `NUMERIC(18,2)` guarda el valor tal cual y suma sin error.

Qué usar
--------
- `campo_dinero()` para importes en pesos. Dos decimales.
- `campo_uvt()` para cantidades de UVT, que no son pesos.
- `campo_cantidad()` para unidades de inventario. Tres decimales, porque hay
  productos que se venden en fracciones (2,5 kg) y porque el costo unitario
  sale de dividir valor entre cantidad: redondear la cantidad a dos decimales
  mete el error por la puerta de atrás.
- `redondear_pesos()` para dejar un importe en centavos exactos. Se llama
  así, y no `pesos()`, porque `core.formato.pesos()` ya existe y hace otra
  cosa: convierte a texto para mostrar («$14.850.000»). Dos funciones con el
  mismo nombre y distinto propósito en módulos distintos es una trampa: en un
  archivo que importa las dos, gana la última importada y el error aparece
  lejos, cuando la base rechaza un «$» en una columna numérica.
- `a_decimal()` para convertir lo que entra de afuera (un Excel, un JSON).
  Convierte desde `str` y no desde `float` a propósito: `Decimal(0.1)` guarda
  el error del float, `Decimal("0.1")` no.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Union

from sqlalchemy import Numeric
from sqlmodel import Field

CERO = Decimal("0")
CENTAVO = Decimal("0.01")
UNIDAD_CANTIDAD = Decimal("0.001")

DINERO = Numeric(18, 2)
CANTIDAD = Numeric(18, 3)
UVT = Numeric(18, 2)


def campo_dinero(**kwargs) -> Field:
    """Columna de dinero. El resto de los argumentos van tal cual a `Field`.

    No pone valor por omisión a propósito: un campo obligatorio con `gt=0` y
    un valor por omisión de cero es una contradicción que no salta hasta que
    alguien omite el campo. Quien declara el campo dice si lleva `default`.
    """
    return Field(sa_type=DINERO, **kwargs)


def campo_cantidad(**kwargs) -> Field:
    """Columna de cantidad de inventario, con tres decimales."""
    return Field(sa_type=CANTIDAD, **kwargs)


def campo_uvt(**kwargs) -> Field:
    """Columna de una cantidad de UVT, que no es dinero.

    Los topes del Estatuto están escritos en UVT y el valor en pesos de la
    UVT cambia cada año. Guardar el tope en UVT y multiplicar al leer es lo
    que hace que un año viejo siga liquidándose con su propia UVT.
    """
    return Field(sa_type=UVT, **kwargs)


def a_decimal(valor: Union[None, int, float, str, Decimal]) -> Optional[Decimal]:
    """Lleva a `Decimal` un valor que viene de afuera, sin arrastrar el error
    del float.

    `None` entra y sale como `None`: la ausencia de dato se conserva.
    """
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def redondear_pesos(valor: Union[None, int, float, str, Decimal]) -> Decimal:
    """Redondea a centavos, con la regla de la mitad hacia arriba.

    `Decimal` no redondea solo: una división deja todos los decimales que
    quepan en la precisión del contexto. Al guardar en `NUMERIC(18,2)` la base
    recorta, así que conviene redondear antes y a la vista, y no descubrir la
    diferencia al releer la fila.
    """
    convertido = a_decimal(valor)
    if convertido is None:
        return CERO
    return convertido.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def redondear_cantidad(valor: Union[None, int, float, str, Decimal]) -> Decimal:
    convertido = a_decimal(valor)
    if convertido is None:
        return CERO
    return convertido.quantize(UNIDAD_CANTIDAD, rounding=ROUND_HALF_UP)
