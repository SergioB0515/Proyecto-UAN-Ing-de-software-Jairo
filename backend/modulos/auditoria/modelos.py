"""Registro de accesos (intentos de inicio de sesión) y de acciones de cada
contador. Ver Incremento 6 en documentacion/05-modelo-desarrollo.md.
"""
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
    BLOQUEADO = "BLOQUEADO"  # intento rechazado sin verificar la contraseña


class IntentoAcceso(SQLModel, table=True):
    """Cada intento de inicio de sesión. Se registra por email aunque ese
    email no exista, para que el bloqueo no revele qué cuentas existen."""

    __tablename__ = "intentos_acceso"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, max_length=255)
    resultado: ResultadoAcceso
    ip: Optional[str] = Field(default=None, max_length=64)
    # timestamptz: el bloqueo compara fechas, y una columna sin zona horaria
    # las desplazaría según la zona del servidor de PostgreSQL.
    fecha: datetime = Field(default_factory=_ahora, index=True, sa_type=DateTime(timezone=True))


class IntentoAccesoLeer(SQLModel):
    resultado: ResultadoAcceso
    ip: Optional[str]
    fecha: datetime


class EventoAuditoria(SQLModel, table=True):
    """Una acción que modificó datos (o descargó un reporte), con quién la
    hizo, sobre qué contribuyente y desde dónde."""

    __tablename__ = "eventos_auditoria"

    id: Optional[int] = Field(default=None, primary_key=True)
    contador_id: int = Field(foreign_key="contadores.id", index=True)
    # Sin llave foránea a propósito: el evento debe sobrevivir a que el
    # contribuyente se elimine.
    contribuyente_id: Optional[int] = Field(default=None, index=True)
    accion: str = Field(max_length=80)  # nombre del endpoint
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
