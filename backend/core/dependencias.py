"""Dependencia get_contador_actual: resuelve el contador autenticado a
partir del token JWT, para usar en cualquier endpoint protegido."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from database import obtener_sesion
from modulos.contadores.modelos import Contador

from .seguridad import decodificar_token

# tokenUrl es solo para que la documentación interactiva (Swagger) sepa
# dónde pedir el token con el botón "Authorize" — no redirige ni valida nada.
_esquema_oauth2 = OAuth2PasswordBearer(tokenUrl="/contadores/login")


def obtener_contador_actual(
    token: str = Depends(_esquema_oauth2),
    session: Session = Depends(obtener_sesion),
) -> Contador:
    error_credenciales = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar la sesión",
        headers={"WWW-Authenticate": "Bearer"},
    )

    email = decodificar_token(token)
    if email is None:
        raise error_credenciales

    contador = session.exec(
        select(Contador).where(Contador.email == email)
    ).first()
    if contador is None:
        raise error_credenciales

    return contador
