from sqlmodel import Session, select

from core.excepciones import ContadorYaExisteError, CredencialesInvalidasError
from core.seguridad import (
    crear_token_acceso,
    hashear_contrasena,
    verificar_contrasena,
)

from .modelos import Contador, ContadorCrear, ContadorLogin


def registrar_contador(session: Session, datos: ContadorCrear) -> Contador:
    """Crea un nuevo contador. Lanza ContadorYaExisteError si el email ya
    está registrado (HU-01)."""
    existente = session.exec(
        select(Contador).where(Contador.email == datos.email)
    ).first()
    if existente is not None:
        raise ContadorYaExisteError(
            f"Ya existe un contador registrado con el email {datos.email}"
        )

    contador = Contador(
        nombre=datos.nombre,
        email=datos.email,
        hash_contrasena=hashear_contrasena(datos.contrasena),
    )
    session.add(contador)
    session.commit()
    session.refresh(contador)
    return contador


def autenticar_contador(session: Session, credenciales: ContadorLogin) -> str:
    """Verifica email y contraseña, y devuelve un token JWT firmado.
    Lanza CredencialesInvalidasError si no coinciden (HU-01). El mensaje es
    deliberadamente genérico para no revelar si el email existe o no."""
    contador = session.exec(
        select(Contador).where(Contador.email == credenciales.email)
    ).first()
    if contador is None or not verificar_contrasena(
        credenciales.contrasena, contador.hash_contrasena
    ):
        raise CredencialesInvalidasError("Email o contraseña incorrectos")

    return crear_token_acceso(sub=contador.email)
