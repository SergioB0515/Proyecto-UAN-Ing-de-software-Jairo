"""Hash de contraseñas y manejo de tokens JWT.

Usa argon2 (vía passlib) en vez de bcrypt, y JWT en vez de sesión de
servidor — ver la justificación en documentacion/04-arquitectura.md.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from core.config import JWT_ALGORITHM, JWT_EXPIRACION_MINUTOS, JWT_SECRET_KEY

_contexto_hash = CryptContext(schemes=["argon2"], deprecated="auto")


def hashear_contrasena(contrasena: str) -> str:
    """Genera el hash argon2 de una contraseña en texto plano."""
    return _contexto_hash.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_almacenado: str) -> bool:
    """Verifica una contraseña en texto plano contra su hash almacenado."""
    return _contexto_hash.verify(contrasena, hash_almacenado)


def crear_token_acceso(sub: str, minutos: Optional[int] = None) -> str:
    """Crea un token JWT firmado, con `sub` (el email del contador) como
    identificador del titular y una expiración configurable."""
    expira = datetime.now(timezone.utc) + timedelta(
        minutes=minutos if minutos is not None else JWT_EXPIRACION_MINUTOS
    )
    payload = {"sub": sub, "exp": expira}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decodificar_token(token: str) -> Optional[str]:
    """Devuelve el `sub` del token si es válido y no ha expirado, o None."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")
