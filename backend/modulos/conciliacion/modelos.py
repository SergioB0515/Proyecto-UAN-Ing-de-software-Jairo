from enum import Enum
from typing import Dict, List, Optional

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
    registro_exogena_id: Optional[int] = None
    nit_reportante: Optional[str] = None
    nombre_reportante: Optional[str] = None
    concepto_code: Optional[str] = None


class ResultadoConciliacion(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    reporte_exogena_id: int
    items: List[ItemConciliacion]
    resumen: Dict[EstadoConciliacion, int]


class RenglonSugerido(SQLModel):
    renglon: str
    valor_total: float
    cantidad_registros: int


class BorradorRenglones(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    reporte_exogena_id: int
    renglones: List[RenglonSugerido]
    advertencia: str = (
        "Valores sugeridos a partir de la columna 'Uso declaración Sugerida' "
        "de la exógena. Son un punto de partida editable, no el valor final "
        "a declarar."
    )
