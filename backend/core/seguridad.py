from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from core.config import JWT_ALGORITHM, JWT_EXPIRACION_MINUTOS, JWT_SECRET_KEY

_contexto_hash = CryptContext(schemes=["argon2"], deprecated="auto")


def hashear_contrasena(contrasena: str) -> str:
    return _contexto_hash.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_almacenado: str) -> bool:
    return _contexto_hash.verify(contrasena, hash_almacenado)


def crear_token_acceso(sub: str, minutos: Optional[int] = None) -> str:
    expira = datetime.now(timezone.utc) + timedelta(
        minutes=minutos if minutos is not None else JWT_EXPIRACION_MINUTOS
    )
    payload = {"sub": sub, "exp": expira}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decodificar_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")
