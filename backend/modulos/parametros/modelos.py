from datetime import date
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, SQLModel


class UmbralDeclaracionBase(SQLModel):
    valor_uvt: float = Field(gt=0)
    tope_ingresos_uvt: float = Field(gt=0)
    tope_patrimonio_uvt: float = Field(gt=0)
    tope_consumo_tc_uvt: float = Field(gt=0)
    tope_compras_uvt: float = Field(gt=0)
    tope_movimiento_uvt: float = Field(gt=0)


class UmbralDeclaracion(UmbralDeclaracionBase, table=True):
    __tablename__ = "umbrales_declaracion"

    anio_gravable: int = Field(primary_key=True, ge=2000, le=2100)


class UmbralDeclaracionCrear(UmbralDeclaracionBase):
    anio_gravable: int = Field(ge=2000, le=2100)


class UmbralDeclaracionLeer(UmbralDeclaracionBase):
    anio_gravable: int


class PlazoDeclaracion(SQLModel, table=True):
    __tablename__ = "plazos_declaracion"

    anio_gravable: int = Field(primary_key=True, ge=2000, le=2100)
    digitos_desde: int = Field(primary_key=True, ge=1, le=100)
    digitos_hasta: int = Field(ge=1, le=100)
    fecha: date


class PlazoDeclaracionDatos(SQLModel):
    digitos_desde: int = Field(ge=1, le=100)
    digitos_hasta: int = Field(ge=1, le=100)
    fecha: date


class PlazoDeclaracionLeer(PlazoDeclaracionDatos):
    anio_gravable: int


class EstadoVencimiento(str, Enum):
    PRESENTADA = "PRESENTADA"
    VENCIDA = "VENCIDA"
    PROXIMA = "PROXIMA"
    PENDIENTE = "PENDIENTE"
    SIN_FECHA = "SIN_FECHA"


class VencimientoDeclaracion(SQLModel):
    estado: EstadoVencimiento
    fecha: Optional[date] = None
    origen: Optional[str] = None
    ultimos_digitos: Optional[str] = None
    dias_restantes: Optional[int] = None
    fecha_presentacion: Optional[date] = None


class DetalleCriterio(SQLModel):
    criterio: str
    valor_reportado: float
    umbral: float
    supera_umbral: bool


class ResultadoObligacion(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    anio_gravable: int
    obligado: bool
    criterios: List[DetalleCriterio]
    advertencia: str = (
        "Este resultado no evalúa el criterio de responsable de IVA "
        "durante el año (no aparece en la información exógena) — "
        "verifícalo aparte. Es una señal de apoyo, no un veredicto legal "
        "completo."
    )
