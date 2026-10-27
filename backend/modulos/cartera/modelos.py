from enum import Enum
from typing import List, Optional

from sqlmodel import SQLModel

from ..contribuyentes.modelos import EstadoPeriodo, TipoContribuyente
from ..parametros.modelos import VencimientoDeclaracion


class OrdenCartera(str, Enum):
    ALERTAS = "alertas"
    NOMBRE = "nombre"
    VENCIMIENTO = "vencimiento"


class FilaCartera(SQLModel):
    contribuyente_id: int
    nombre: str
    rut: str
    tipo_contribuyente: TipoContribuyente
    periodo_fiscal_id: Optional[int] = None
    anio_gravable: Optional[int] = None
    estado_periodo: Optional[EstadoPeriodo] = None
    obligado: Optional[bool] = None
    alertas_no_declarado: Optional[int] = None
    vencimiento: Optional[VencimientoDeclaracion] = None
    avisos: List[str] = []


class PanelCartera(SQLModel):
    anio_gravable: Optional[int]
    total_contribuyentes: int
    total_obligados: int
    total_alertas: int
    total_vencidas: int = 0
    total_proximas: int = 0
    contribuyentes: List[FilaCartera]
