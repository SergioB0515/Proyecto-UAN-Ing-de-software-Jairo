import os

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from database import obtener_sesion
from modulos.contadores.modelos import Contador

from .seguridad import decodificar_token

# El prefijo debe coincidir con PREFIJO_API de main.py: solo afecta al botón
# «Authorize» de /docs, pero sin esto deja de funcionar en el despliegue.
_PREFIJO_API = os.getenv("PREFIJO_API", "").rstrip("/")

_esquema_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{_PREFIJO_API}/contadores/login")


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
