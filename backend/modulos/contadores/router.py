from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import ContadorYaExisteError, CredencialesInvalidasError
from database import obtener_sesion

from . import servicios
from .modelos import Contador, ContadorCrear, ContadorLeer, ContadorLogin, Token

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
    # OAuth2PasswordRequestForm exige los campos "username"/"password" en
    # form-data — es el estándar que espera el flujo OAuth2 de FastAPI.
    # Aquí "username" es el email del contador.
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(obtener_sesion),
) -> Token:
    """HU-01: iniciar sesión y obtener un token JWT."""
    credenciales = ContadorLogin(email=form.username, contrasena=form.password)
    try:
        token = servicios.autenticar_contador(session, credenciales)
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
