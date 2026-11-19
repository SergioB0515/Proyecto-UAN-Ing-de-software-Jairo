"""Política de tratamiento de datos, versionada.

Por qué versionada y no un texto fijo
-------------------------------------
Lo que se guarda al aceptar no es «aceptó»: es «aceptó *esta* redacción, este
día». Si mañana cambia la finalidad del tratamiento y el texto se edita sobre
el mismo registro, las autorizaciones viejas quedarían respaldando un texto
que el titular nunca leyó, y la autorización dejaría de servir como prueba
(Ley 1581 de 2012, art. 9: la autorización es previa, expresa e informada).

Por eso cada redacción entra como una versión nueva y las anteriores se
conservan: `AutorizacionTratamiento` guarda la versión que el titular aceptó,
y desde ahí siempre se puede reconstruir qué decía el texto ese día.

Para publicar una redacción nueva se agrega una entrada a VERSIONES con una
versión mayor; no se edita una existente.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional


@dataclass(frozen=True)
class VersionPolitica:
    version: str
    vigente_desde: date
    titulo: str
    # Finalidades concretas. Una autorización "para lo que sea necesario" no
    # es informada: el titular tiene que poder leer para qué se usa el dato.
    finalidades: List[str]
    responsable: str
    derechos: str
    texto: str


_V1 = VersionPolitica(
    version="2026.1",
    vigente_desde=date(2026, 1, 1),
    titulo="Autorización para el tratamiento de datos personales",
    finalidades=[
        "Recibir los soportes y la información que usted cargue para preparar "
        "su declaración de renta del año gravable indicado.",
        "Cruzar esa información con la que terceros le reportaron a la DIAN, "
        "para detectar diferencias antes de presentar la declaración.",
        "Conservar los soportes como respaldo de la declaración durante el "
        "término en que la DIAN puede revisarla.",
    ],
    responsable=(
        "El contador o la firma contable que le envió este enlace. Es quien "
        "responde por sus datos; esta aplicación es la herramienta que usa."
    ),
    derechos=(
        "Usted puede conocer, actualizar, rectificar y solicitar la supresión "
        "de sus datos, y revocar esta autorización, escribiéndole a su "
        "contador. La supresión no procede mientras exista un deber legal de "
        "conservar los soportes de una declaración ya presentada."
    ),
    texto=(
        "Autorizo de manera previa, expresa e informada a mi contador para "
        "recolectar, almacenar y usar los datos personales y los documentos "
        "que cargue en este enlace, con la única finalidad de preparar y "
        "soportar mi declaración de renta del año gravable indicado. "
        "Entiendo que mis datos no se usarán para otra finalidad ni se "
        "entregarán a terceros distintos de la DIAN en el cumplimiento de esa "
        "obligación, y que puedo revocar esta autorización en cualquier "
        "momento en los términos de la Ley 1581 de 2012."
    ),
)


VERSIONES: Dict[str, VersionPolitica] = {_V1.version: _V1}

# Redacción que se le muestra a quien abre el enlace hoy.
VERSION_VIGENTE = _V1.version


def vigente() -> VersionPolitica:
    return VERSIONES[VERSION_VIGENTE]


def obtener(version: str) -> Optional[VersionPolitica]:
    """La redacción que el titular aceptó, aunque ya no sea la vigente."""
    return VERSIONES.get(version)
