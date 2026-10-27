from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from sqlmodel import Field, SQLModel

from ..conciliacion.modelos import EstadoConciliacion
from ..contribuyentes.modelos import EstadoPeriodo, TipoContribuyente
from ..parametros.modelos import ResultadoObligacion, VencimientoDeclaracion


class TipoReporte(str, Enum):
    KARDEX = "kardex"
    SALDO_INVENTARIO = "saldo-inventario"
    CONCILIACION = "conciliacion"
    BORRADOR_RENGLONES = "borrador-renglones"
    RESUMEN = "resumen"


class FormatoReporte(str, Enum):
    XLSX = "xlsx"
    PDF = "pdf"


class CierrePeriodo(SQLModel, table=True):
    __tablename__ = "cierres_periodo"

    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    fecha_cierre: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valor_inventario: float = 0.0
    costo_ventas: float = 0.0
    activo_inventario_id: Optional[int] = Field(default=None, foreign_key="activos.id")


class CierrePeriodoLeer(SQLModel):
    periodo_fiscal_id: int
    contribuyente_id: int
    anio_gravable: int
    estado: EstadoPeriodo
    fecha_cierre: datetime
    valor_inventario: float
    costo_ventas: float
    activo_inventario_id: Optional[int]


class ResumenPatrimonio(SQLModel):
    patrimonio_liquido: float
    por_tipo: Dict[str, float]


class ResumenIngresos(SQLModel):
    cantidad_fuentes: int
    total_ingresos: float
    total_retenciones: float


class ResumenInventario(SQLModel):
    cantidad_productos: int
    total_ingresos_ventas: float
    total_costo_ventas: float
    total_utilidad_bruta: float
    inventario_final: float


class ResumenContribuyente(SQLModel):
    contribuyente_id: int
    nombre: str
    rut: str
    tipo_contribuyente: TipoContribuyente
    regimen_tributario: str
    periodo_fiscal_id: int
    anio_gravable: int
    estado_periodo: EstadoPeriodo
    cierre: Optional[CierrePeriodoLeer] = None
    patrimonio: ResumenPatrimonio
    ingresos: ResumenIngresos
    inventario: Optional[ResumenInventario] = None
    obligacion: Optional[ResultadoObligacion] = None
    vencimiento: Optional[VencimientoDeclaracion] = None
    conciliacion: Optional[Dict[EstadoConciliacion, int]] = None
    avisos: List[str] = []
