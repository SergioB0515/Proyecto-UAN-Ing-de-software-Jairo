from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Index
from sqlmodel import Field, SQLModel


class TipoEntidadAdjunto(str, Enum):
    CONTRIBUYENTE = "CONTRIBUYENTE"
    PERIODO_FISCAL = "PERIODO_FISCAL"
    ACTIVO = "ACTIVO"
    FUENTE_INGRESO = "FUENTE_INGRESO"
    DOCUMENTO_SOPORTE = "DOCUMENTO_SOPORTE"
    MOVIMIENTO = "MOVIMIENTO"
    PROVEEDOR = "PROVEEDOR"


class CategoriaAdjunto(str, Enum):
    RECIBO = "RECIBO"
    FACTURA = "FACTURA"
    TRANSFERENCIA = "TRANSFERENCIA"
    CAPTURA = "CAPTURA"
    CERTIFICADO = "CERTIFICADO"
    DECLARACION = "DECLARACION"
    CONTRATO = "CONTRATO"
    OTRO = "OTRO"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Adjunto(SQLModel, table=True):
    __tablename__ = "adjuntos"
    __table_args__ = (Index("ix_adjuntos_entidad", "contribuyente_id", "entidad_tipo", "entidad_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    entidad_tipo: TipoEntidadAdjunto
    entidad_id: int
    periodo_fiscal_id: Optional[int] = Field(default=None, foreign_key="periodos_fiscales.id", index=True)
    categoria: CategoriaAdjunto = Field(default=CategoriaAdjunto.OTRO)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    nombre_original: str = Field(max_length=255)
    ruta_relativa: str = Field(max_length=300)
    tipo_mime: str = Field(max_length=100)
    tamano_bytes: int
    sha256: str = Field(max_length=64, index=True)
    creado_en: datetime = Field(default_factory=_ahora, sa_type=DateTime(timezone=True))


class AdjuntoActualizar(SQLModel):
    descripcion: Optional[str] = Field(default=None, max_length=300)
    categoria: Optional[CategoriaAdjunto] = None


class AdjuntoLeer(SQLModel):
    id: int
    contribuyente_id: int
    entidad_tipo: TipoEntidadAdjunto
    entidad_id: int
    etiqueta_entidad: Optional[str] = None
    periodo_fiscal_id: Optional[int]
    categoria: CategoriaAdjunto
    descripcion: Optional[str]
    nombre_original: str
    tipo_mime: str
    tamano_bytes: int
    creado_en: datetime
    previsualizable: bool


class ConteoAdjuntos(SQLModel):
    entidad_tipo: TipoEntidadAdjunto
    entidad_id: int
    total: int
