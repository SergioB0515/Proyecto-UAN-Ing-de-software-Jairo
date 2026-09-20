"""Contador: el profesional que se autentica y gestiona su cartera de
contribuyentes. Ver documentacion/07-diagrama-clases.md.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class ContadorBase(SQLModel):
    nombre: str = Field(min_length=1, max_length=120)
    email: str = Field(index=True, unique=True, max_length=255)


class Contador(ContadorBase, table=True):
    __tablename__ = "contadores"

    id: Optional[int] = Field(default=None, primary_key=True)
    hash_contrasena: str
    creado_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ContadorCrear(ContadorBase):
    """Lo que llega en el body de POST /contadores/registro."""

    contrasena: str = Field(min_length=8, max_length=128)


class ContadorLeer(ContadorBase):
    """Lo que se devuelve al cliente — nunca incluye el hash de la
    contraseña."""

    id: int
    creado_en: datetime


class ContadorLogin(SQLModel):
    email: str
    contrasena: str


class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"
