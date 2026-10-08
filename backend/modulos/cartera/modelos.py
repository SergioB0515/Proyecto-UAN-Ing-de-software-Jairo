"""Panel de cartera (HU-18, Proceso 11). Sin tablas propias: agrega lo que
ya calculan parametros (obligación) y conciliacion (alertas) para todos los
contribuyentes del contador.
"""
from enum import Enum
from typing import List, Optional

from sqlmodel import SQLModel

from ..contribuyentes.modelos import EstadoPeriodo, TipoContribuyente


class OrdenCartera(str, Enum):
    ALERTAS = "alertas"  # más alertas NO_DECLARADO primero
    NOMBRE = "nombre"


class FilaCartera(SQLModel):
    contribuyente_id: int
    nombre: str
    rut: str
    tipo_contribuyente: TipoContribuyente
    # None si el contribuyente no tiene periodo para el año pedido.
    periodo_fiscal_id: Optional[int] = None
    anio_gravable: Optional[int] = None
    estado_periodo: Optional[EstadoPeriodo] = None
    # None si falta la exógena o el umbral del año (motivo en avisos).
    obligado: Optional[bool] = None
    alertas_no_declarado: Optional[int] = None
    avisos: List[str] = []


class PanelCartera(SQLModel):
    anio_gravable: Optional[int]
    total_contribuyentes: int
    total_obligados: int
    total_alertas: int
    contribuyentes: List[FilaCartera]
