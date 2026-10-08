"""Contador: el profesional que se autentica y gestiona su cartera de
contribuyentes. Ver documentacion/07-diagrama-clases.md.
"""
from datetime import datetime, timezone
from typing import Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel


def validar_contrasena(contrasena: str) -> str:
    """Política mínima: 8 caracteres o más, con al menos una letra y un
    número. Se aplica al registrarse y al cambiar la contraseña."""
    if len(contrasena) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    if not any(c.isalpha() for c in contrasena) or not any(c.isdigit() for c in contrasena):
        raise ValueError("La contraseña debe tener al menos una letra y un número")
    return contrasena


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

    contrasena: str = Field(max_length=128)

    @field_validator("contrasena")
    @classmethod
    def _politica(cls, contrasena: str) -> str:
        return validar_contrasena(contrasena)


class ContadorLeer(ContadorBase):
    """Lo que se devuelve al cliente — nunca incluye el hash de la
    contraseña."""

    id: int
    creado_en: datetime


class CambioContrasena(SQLModel):
    contrasena_actual: str
    contrasena_nueva: str = Field(max_length=128)

    @field_validator("contrasena_nueva")
    @classmethod
    def _politica(cls, contrasena: str) -> str:
        return validar_contrasena(contrasena)


class ContadorLogin(SQLModel):
    email: str
    contrasena: str


class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"
