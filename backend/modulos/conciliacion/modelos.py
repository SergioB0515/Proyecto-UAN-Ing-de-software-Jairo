
from enum import Enum
from typing import List, Optional

from sqlmodel import SQLModel


class OrigenItemConciliacion(str, Enum):
    ACTIVO = "Activo"
    FUENTE_INGRESO = "FuenteIngreso"
    EXOGENA = "Exógena"


class EstadoConciliacion(str, Enum):
    COINCIDE = "COINCIDE"
    DISCREPANCIA = "DISCREPANCIA"
    NO_DECLARADO = "NO_DECLARADO"
    NO_REPORTADO_POR_TERCERO = "NO_REPORTADO_POR_TERCERO"


class ItemConciliacion(SQLModel):
    concepto: str
    origen: OrigenItemConciliacion
    valor_declarado: Optional[float] = None
    valor_exogena: Optional[float] = None
    diferencia: Optional[float] = None
    estado: EstadoConciliacion


class ResultadoConciliacion(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    items: List[ItemConciliacion]


class RenglonSugerido(SQLModel):
    renglon: str
    valor_total: float
    cantidad_registros: int


class BorradorRenglones(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    renglones: List[RenglonSugerido]