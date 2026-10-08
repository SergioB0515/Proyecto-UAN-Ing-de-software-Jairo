"""Categoria, Producto y MetodoCosteo. Ver documentacion/07-diagrama-clases.md
(módulo de inventario) y HU-11 en documentacion/06-historias-usuario.md.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class MetodoCosteo(str, Enum):
    PEPS = "PEPS"
    PROMEDIO_PONDERADO = "PROMEDIO_PONDERADO"


class ClasificacionIva(str, Enum):
    GRAVADO = "GRAVADO"
    EXENTO = "EXENTO"
    EXCLUIDO = "EXCLUIDO"


# -------------------------------------------------------------------- Categoria


class CategoriaBase(SQLModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=300)


class Categoria(CategoriaBase, table=True):
    __tablename__ = "categorias"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)

    # Agregación, no composición: eliminar la categoría no elimina sus
    # productos (HU-11).
    productos: List["Producto"] = Relationship(back_populates="categoria")


class CategoriaCrear(CategoriaBase):
    pass


class CategoriaLeer(CategoriaBase):
    id: int
    contribuyente_id: int


# --------------------------------------------------------------------- Producto


class ProductoBase(SQLModel):
    codigo: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=1, max_length=200)
    clasificacion_iva: ClasificacionIva
    metodo_costeo: MetodoCosteo
    categoria_id: Optional[int] = Field(default=None, foreign_key="categorias.id")


class Producto(ProductoBase, table=True):
    __tablename__ = "productos"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    activo: bool = Field(default=True)
    # Lo actualiza el registro de movimientos (Proceso 8, modulos/movimientos),
    # nunca el CRUD de productos.
    stock_actual: float = Field(default=0, ge=0)
    creado_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    categoria: Optional[Categoria] = Relationship(back_populates="productos")


class ProductoCrear(ProductoBase):
    pass


class ProductoActualizar(SQLModel):
    """Todos los campos opcionales: solo se cambia lo que venga."""

    nombre: Optional[str] = Field(default=None, min_length=1, max_length=200)
    clasificacion_iva: Optional[ClasificacionIva] = None
    metodo_costeo: Optional[MetodoCosteo] = None
    categoria_id: Optional[int] = None
    activo: Optional[bool] = None


class ProductoLeer(ProductoBase):
    id: int
    contribuyente_id: int
    activo: bool
    stock_actual: float
    creado_en: datetime
