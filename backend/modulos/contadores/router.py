from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ContadorYaExisteError,
    ContrasenaActualIncorrectaError,
    CredencialesInvalidasError,
    CuentaBloqueadaError,
)
from database import obtener_sesion

from . import servicios
from ..auditoria.middleware import ip_cliente
from .modelos import CambioContrasena, Contador, ContadorCrear, ContadorLeer, ContadorLogin, Token

router = APIRouter(prefix="/contadores", tags=["contadores"])


@router.post(
    "/registro", response_model=ContadorLeer, status_code=status.HTTP_201_CREATED
)
def registro(
    datos: ContadorCrear, session: Session = Depends(obtener_sesion)
) -> Contador:
    """HU-01: crear una cuenta de contador."""
    try:
        return servicios.registrar_contador(session, datos)
    except ContadorYaExisteError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.post("/login", response_model=Token)
def login(
    request: Request,
    # OAuth2PasswordRequestForm exige los campos "username"/"password" en
    # form-data — es el estándar que espera el flujo OAuth2 de FastAPI.
    # Aquí "username" es el email del contador.
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(obtener_sesion),
) -> Token:
    """HU-01: iniciar sesión y obtener un token JWT. 429 si el email está
    bloqueado por intentos fallidos (con `Retry-After` en segundos)."""
    credenciales = ContadorLogin(email=form.username, contrasena=form.password)
    try:
        token = servicios.autenticar_contador(session, credenciales, ip_cliente(request))
    except CuentaBloqueadaError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.segundos)},
        ) from exc
    except CredencialesInvalidasError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return Token(access_token=token)


@router.get("/yo", response_model=ContadorLeer)
def yo(contador: Contador = Depends(obtener_contador_actual)) -> Contador:
    """Devuelve el contador autenticado — útil para que el frontend
    verifique si el token guardado sigue siendo válido."""
    return contador


@router.put("/yo/contrasena", status_code=status.HTTP_204_NO_CONTENT)
def cambiar_contrasena(
    datos: CambioContrasena,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Cambia la contraseña del contador autenticado. 400 si la actual no
    coincide; 422 si la nueva no cumple la política."""
    try:
        servicios.cambiar_contrasena(session, contador, datos)
    except ContrasenaActualIncorrectaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
