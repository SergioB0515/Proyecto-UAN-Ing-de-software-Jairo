"""ReporteExogena, RegistroExogena, TopeExogena y ConceptoDian. Ver
documentacion/07-diagrama-clases.md y documentacion/03-logica-proyecto.md
(Proceso 4).

Los campos y la forma de estas clases están probados contra un archivo real
de la DIAN; modulos/exogena/servicios.py los llena a partir del Excel.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Field, SQLModel

# ------------------------------------------------------------- ConceptoDian


class ConceptoDian(SQLModel, table=True):
    """Catálogo de referencia: código DIAN -> descripción/categoría. Se va
    completando con el uso (HU nueva, ver conversación) — no es un listado
    cerrado que haya que poblar de una vez.
    """

    __tablename__ = "conceptos_dian"

    codigo: str = Field(primary_key=True, max_length=10)
    descripcion: str = Field(max_length=300)
    categoria: Optional[str] = Field(default=None, max_length=60)


# ----------------------------------------------------------- ReporteExogena


class ReporteExogenaBase(SQLModel):
    nombre_archivo_original: str = Field(max_length=255)


class ReporteExogena(ReporteExogenaBase, table=True):
    __tablename__ = "reportes_exogena"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)
    fecha_importacion: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ReporteExogenaLeer(ReporteExogenaBase):
    id: int
    contribuyente_id: int
    periodo_fiscal_id: int
    fecha_importacion: datetime


# ---------------------------------------------------------- RegistroExogena


class RegistroExogenaBase(SQLModel):
    nit_reportante: str = Field(max_length=20)
    nombre_reportante: str = Field(max_length=300)
    detalle: str = Field(max_length=500)
    # Extraído de "Detalle" con regex — no todas las filas lo traen.
    concepto_code: Optional[str] = Field(default=None, max_length=10)
    # Extraído de "Uso declaración Sugerida" con regex — puede haber más de
    # uno por fila; se guardan separados por coma (ej. "R29, R30").
    renglones_sugeridos: Optional[str] = Field(default=None, max_length=100)
    valor: float
    uso_sugerido: Optional[str] = Field(default=None, max_length=500)
    info_adicional: Optional[str] = Field(default=None, max_length=1000)
    # True si nit_reportante == identificación del consultante (dato propio,
    # no un cruce real con un tercero).
    es_auto_reportado: bool = Field(default=False)
    # True si nit_reportante es el NIT de la propia DIAN (800197268).
    es_dian: bool = Field(default=False)


class RegistroExogena(RegistroExogenaBase, table=True):
    __tablename__ = "registros_exogena"

    id: Optional[int] = Field(default=None, primary_key=True)
    reporte_exogena_id: int = Field(
        foreign_key="reportes_exogena.id", index=True
    )


class RegistroExogenaLeer(RegistroExogenaBase):
    id: int
    reporte_exogena_id: int


# -------------------------------------------------------------- TopeExogena


class TopeExogenaBase(SQLModel):
    etiqueta: str = Field(max_length=100)  # ej. "Tope 1 - Ingresos"
    valor: float


class TopeExogena(TopeExogenaBase, table=True):
    __tablename__ = "topes_exogena"

    id: Optional[int] = Field(default=None, primary_key=True)
    reporte_exogena_id: int = Field(
        foreign_key="reportes_exogena.id", index=True
    )


class TopeExogenaLeer(TopeExogenaBase):
    id: int
    reporte_exogena_id: int


# ------------------------------------------------ Clases de resultado (no persisten)
# Estas NO son tablas — son la forma en que modulos/exogena/servicios.py
# devuelve el resultado de parsear un archivo, antes de decidir si se
# guarda. Ver el docstring de parsear_archivo_exogena en servicios.py.


class ConsultanteInfo(SQLModel):
    tipo_documento: Optional[str] = None
    identificacion: Optional[str] = None
    nombre: Optional[str] = None


class FilaConError(SQLModel):
    fila: int
    motivo: str


class ResultadoParseo(SQLModel):
    consultante: ConsultanteInfo
    topes: List[TopeExogenaBase] = []
    registros: List[RegistroExogenaBase] = []
    errores: List[FilaConError] = []


class ReporteExogenaImportado(ReporteExogenaLeer):
    """Respuesta de la importación (HU-05): el reporte guardado más el
    resumen de lo leído, incluidas las filas que no se pudieron interpretar
    — se informan al contador en vez de descartarse en silencio."""

    consultante: ConsultanteInfo
    cantidad_topes: int
    cantidad_registros: int
    errores: List[FilaConError] = []
