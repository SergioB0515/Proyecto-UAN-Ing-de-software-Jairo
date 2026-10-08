"""Resultados de la conciliación (HU-08, HU-09) y del borrador de renglones
(HU-10). Ninguna de estas clases es tabla: se calculan al momento de la
consulta para no quedar desactualizadas si se corrige un dato después
(documentacion/07-diagrama-clases.md).
"""
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
    # valor_exogena - valor_declarado: positiva si la DIAN ve más de lo
    # declarado.
    diferencia: Optional[float] = None
    estado: EstadoConciliacion
    # Del RegistroExogena cruzado (o no declarado), cuando lo hay.
    registro_exogena_id: Optional[int] = None
    nit_reportante: Optional[str] = None
    nombre_reportante: Optional[str] = None
    concepto_code: Optional[str] = None


class ResultadoConciliacion(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    reporte_exogena_id: int
    items: List[ItemConciliacion]
    # Cantidad de ítems por estado; NO_DECLARADO es el número de alertas
    # que usará el panel de cartera (HU-18).
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
