from sqlmodel import Session, select

from typing import Optional

from core.excepciones import (
    ContadorYaExisteError,
    ContrasenaActualIncorrectaError,
    CredencialesInvalidasError,
)
from core.seguridad import (
    crear_token_acceso,
    hashear_contrasena,
    verificar_contrasena,
)

from ..auditoria.modelos import ResultadoAcceso
from ..auditoria.servicios import registrar_intento, verificar_no_bloqueado
from .modelos import CambioContrasena, Contador, ContadorCrear, ContadorLogin


def registrar_contador(session: Session, datos: ContadorCrear) -> Contador:
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


def autenticar_contador(
    session: Session, credenciales: ContadorLogin, ip: Optional[str] = None
) -> str:
    verificar_no_bloqueado(session, credenciales.email, ip)
    contador = session.exec(
        select(Contador).where(Contador.email == credenciales.email)
    ).first()
    if contador is None or not verificar_contrasena(
        credenciales.contrasena, contador.hash_contrasena
    ):
        registrar_intento(session, credenciales.email, ResultadoAcceso.FALLIDO, ip)
        raise CredencialesInvalidasError("Email o contraseña incorrectos")

    registrar_intento(session, credenciales.email, ResultadoAcceso.EXITOSO, ip)
    return crear_token_acceso(sub=contador.email)


def cambiar_contrasena(session: Session, contador: Contador, datos: CambioContrasena) -> None:
    if not verificar_contrasena(datos.contrasena_actual, contador.hash_contrasena):
        raise ContrasenaActualIncorrectaError("La contraseña actual no es correcta")
    contador.hash_contrasena = hashear_contrasena(datos.contrasena_nueva)
    session.add(contador)
    session.commit()
