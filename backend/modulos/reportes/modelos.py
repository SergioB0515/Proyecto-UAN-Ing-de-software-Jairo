"""CierrePeriodo (la única tabla del módulo) y los resultados calculados del
resumen por contribuyente. Ver Procesos 10 y 11 de
documentacion/03-logica-proyecto.md y HU-15 a HU-17.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from sqlmodel import Field, SQLModel

from ..conciliacion.modelos import EstadoConciliacion
from ..contribuyentes.modelos import EstadoPeriodo, TipoContribuyente
from ..parametros.modelos import ResultadoObligacion


class TipoReporte(str, Enum):
    KARDEX = "kardex"
    SALDO_INVENTARIO = "saldo-inventario"
    CONCILIACION = "conciliacion"
    BORRADOR_RENGLONES = "borrador-renglones"
    RESUMEN = "resumen"


class FormatoReporte(str, Enum):
    XLSX = "xlsx"
    PDF = "pdf"


# ---------------------------------------------------------------- CierrePeriodo


class CierrePeriodo(SQLModel, table=True):
    """Lo que hizo el cierre de un periodo (HU-15), para poder mostrarlo y
    deshacerlo al reabrir: el Activo INVENTARIO que creó y los valores con
    que cerró."""

    __tablename__ = "cierres_periodo"

    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    fecha_cierre: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valor_inventario: float = 0.0
    costo_ventas: float = 0.0
    # None si el contribuyente no maneja inventario (ASALARIADO).
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


# ------------------------------------------------ Clases de resultado (no persisten)


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
    """HU-17: todo lo de un contribuyente para un periodo, en un solo lugar.
    `inventario` es None para un ASALARIADO; `obligacion` y `conciliacion`
    son None si aún no hay exógena o umbral (el motivo va en `avisos`)."""

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
    conciliacion: Optional[Dict[EstadoConciliacion, int]] = None
    avisos: List[str] = []
