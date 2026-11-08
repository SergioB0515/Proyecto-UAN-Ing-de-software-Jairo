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
    casilla: Optional[int] = None
    nombre_oficial: Optional[str] = None


class RegistroSinAsignar(SQLModel):
    """Un valor que la DIAN no asignó a un renglón concreto.

    Trae el menú de renglones posibles para que el contador escoja. No se suma
    a ninguno: la DIAN está diciendo «depende del bien», y repartirlo en todos
    contaría la misma plata varias veces.
    """

    detalle: str
    valor: float
    renglones_posibles: List[str]
    uso_sugerido: Optional[str] = None


class CuadreTope(SQLModel):
    """Contraste del borrador contra los topes que trae el mismo archivo."""

    etiqueta: str
    valor_tope: float
    valor_borrador: float
    diferencia: float
    cuadra: bool


class BorradorRenglones(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    reporte_exogena_id: int
    renglones: List[RenglonSugerido]
    sin_asignar: List[RegistroSinAsignar] = []
    cuadres: List[CuadreTope] = []
    diagnosticos: List[str] = []
    advertencia: str = (
        "Valores sugeridos a partir de la columna 'Uso declaración Sugerida' "
        "de la exógena. Son un punto de partida editable, no el valor final "
        "a declarar."
    )
