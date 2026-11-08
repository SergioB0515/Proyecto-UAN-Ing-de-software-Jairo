from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Field, SQLModel


class ConceptoDian(SQLModel, table=True):
    __tablename__ = "conceptos_dian"

    codigo: str = Field(primary_key=True, max_length=10)
    descripcion: str = Field(max_length=300)
    categoria: Optional[str] = Field(default=None, max_length=60)


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


class RegistroExogenaBase(SQLModel):
    nit_reportante: str = Field(max_length=20)
    nombre_reportante: str = Field(max_length=300)
    detalle: str = Field(max_length=500)
    concepto_code: Optional[str] = Field(default=None, max_length=10)
    renglones_sugeridos: Optional[str] = Field(default=None, max_length=100)
    valor: float
    uso_sugerido: Optional[str] = Field(default=None, max_length=500)
    # True cuando la DIAN ofrece varios renglones posibles en vez de asignar
    # uno. Esos valores NO se suman a ningún renglón: los asigna el contador.
    renglones_son_condicionales: bool = Field(default=False)
    info_adicional: Optional[str] = Field(default=None, max_length=1000)
    es_auto_reportado: bool = Field(default=False)
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


class TopeExogenaBase(SQLModel):
    etiqueta: str = Field(max_length=100)
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
    consultante: ConsultanteInfo
    cantidad_topes: int
    cantidad_registros: int
    errores: List[FilaConError] = []
