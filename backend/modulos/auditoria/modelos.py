from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class ResultadoAcceso(str, Enum):
    EXITOSO = "EXITOSO"
    FALLIDO = "FALLIDO"
    BLOQUEADO = "BLOQUEADO"


class IntentoAcceso(SQLModel, table=True):
    __tablename__ = "intentos_acceso"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, max_length=255)
    resultado: ResultadoAcceso
    ip: Optional[str] = Field(default=None, max_length=64)
    fecha: datetime = Field(default_factory=_ahora, index=True, sa_type=DateTime(timezone=True))


class IntentoAccesoLeer(SQLModel):
    resultado: ResultadoAcceso
    ip: Optional[str]
    fecha: datetime


class EventoAuditoria(SQLModel, table=True):
    __tablename__ = "eventos_auditoria"

    id: Optional[int] = Field(default=None, primary_key=True)
    contador_id: int = Field(foreign_key="contadores.id", index=True)
    contribuyente_id: Optional[int] = Field(default=None, index=True)
    accion: str = Field(max_length=80)
    descripcion: str = Field(max_length=200)
    metodo: str = Field(max_length=10)
    ruta: str = Field(max_length=300)
    ip: Optional[str] = Field(default=None, max_length=64)
    fecha: datetime = Field(default_factory=_ahora, index=True, sa_type=DateTime(timezone=True))


class EventoAuditoriaLeer(SQLModel):
    id: int
    contribuyente_id: Optional[int]
    nombre_contribuyente: Optional[str] = None
    accion: str
    descripcion: str
    metodo: str
    ruta: str
    ip: Optional[str]
    fecha: datetime
