from datetime import date, datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import field_validator
from sqlmodel import Field, Relationship, SQLModel


class TipoContribuyente(str, Enum):
    ASALARIADO = "ASALARIADO"
    INDEPENDIENTE = "INDEPENDIENTE"
    MIXTO = "MIXTO"


class TipoActivo(str, Enum):
    CUENTA = "CUENTA"
    VEHICULO = "VEHICULO"
    INMUEBLE = "INMUEBLE"
    INVERSION = "INVERSION"
    INVENTARIO = "INVENTARIO"


class ContribuyenteBase(SQLModel):
    nombre: str = Field(min_length=1, max_length=200)
    rut: str = Field(index=True, max_length=20)
    tipo_contribuyente: TipoContribuyente
    regimen_tributario: str = Field(default="Ordinario", max_length=60)


class Contribuyente(ContribuyenteBase, table=True):
    __tablename__ = "contribuyentes"

    id: Optional[int] = Field(default=None, primary_key=True)
    contador_id: int = Field(foreign_key="contadores.id", index=True)
    creado_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    activos: List["Activo"] = Relationship(back_populates="contribuyente")
    fuentes_ingreso: List["FuenteIngreso"] = Relationship(
        back_populates="contribuyente"
    )


class ContribuyenteCrear(ContribuyenteBase):
    pass


class ContribuyenteActualizar(SQLModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=200)
    rut: Optional[str] = Field(default=None, min_length=1, max_length=20)
    tipo_contribuyente: Optional[TipoContribuyente] = None
    regimen_tributario: Optional[str] = Field(default=None, max_length=60)


class ContribuyenteLeer(ContribuyenteBase):
    id: int
    contador_id: int
    creado_en: datetime


class ContribuyenteConPatrimonio(ContribuyenteLeer):
    patrimonio_liquido: float
    periodo_fiscal_id: Optional[int] = None
    anio_gravable: Optional[int] = None


class ActivoBase(SQLModel):
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)
    descripcion: str = Field(min_length=1, max_length=200)
    tipo: TipoActivo
    valor: float = Field(gt=0)
    vinculo_codigo_concepto: Optional[str] = Field(default=None, max_length=10)
    vinculo_palabra_clave: Optional[str] = Field(default=None, max_length=200)


class Activo(ActivoBase, table=True):
    __tablename__ = "activos"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)

    contribuyente: Optional[Contribuyente] = Relationship(
        back_populates="activos"
    )


class ActivoCrear(ActivoBase):
    @field_validator("tipo")
    @classmethod
    def _inventario_solo_por_cierre(cls, tipo: TipoActivo) -> TipoActivo:
        if tipo == TipoActivo.INVENTARIO:
            raise ValueError(
                "Un activo INVENTARIO solo lo crea el cierre del periodo fiscal"
            )
        return tipo


class ActivoActualizar(SQLModel):
    descripcion: Optional[str] = Field(default=None, min_length=1, max_length=200)
    tipo: Optional[TipoActivo] = None
    valor: Optional[float] = Field(default=None, gt=0)
    vinculo_codigo_concepto: Optional[str] = Field(default=None, max_length=10)
    vinculo_palabra_clave: Optional[str] = Field(default=None, max_length=200)

    @field_validator("tipo")
    @classmethod
    def _inventario_solo_por_cierre(cls, tipo: Optional[TipoActivo]) -> Optional[TipoActivo]:
        if tipo == TipoActivo.INVENTARIO:
            raise ValueError(
                "Un activo INVENTARIO solo lo crea el cierre del periodo fiscal"
            )
        return tipo


class ActivoLeer(ActivoBase):
    id: int
    contribuyente_id: int
    valor: float


class FuenteIngresoBase(SQLModel):
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)
    concepto: str = Field(min_length=1, max_length=200)
    valor_anual: float = Field(gt=0)
    retencion_fuente: float = Field(default=0, ge=0)
    vinculo_codigo_concepto: Optional[str] = Field(default=None, max_length=10)
    vinculo_palabra_clave: Optional[str] = Field(default=None, max_length=200)


class FuenteIngreso(FuenteIngresoBase, table=True):
    __tablename__ = "fuentes_ingreso"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)

    contribuyente: Optional[Contribuyente] = Relationship(
        back_populates="fuentes_ingreso"
    )


class FuenteIngresoCrear(FuenteIngresoBase):
    pass


class FuenteIngresoActualizar(SQLModel):
    concepto: Optional[str] = Field(default=None, min_length=1, max_length=200)
    valor_anual: Optional[float] = Field(default=None, gt=0)
    retencion_fuente: Optional[float] = Field(default=None, ge=0)
    vinculo_codigo_concepto: Optional[str] = Field(default=None, max_length=10)
    vinculo_palabra_clave: Optional[str] = Field(default=None, max_length=200)


class FuenteIngresoLeer(FuenteIngresoBase):
    id: int
    contribuyente_id: int


class EstadoPeriodo(str, Enum):
    ABIERTO = "ABIERTO"
    CERRADO = "CERRADO"


class PeriodoFiscalBase(SQLModel):
    anio_gravable: int = Field(ge=2000, le=2100)
    estado: EstadoPeriodo = Field(default=EstadoPeriodo.ABIERTO)
    fecha_vencimiento_manual: Optional[date] = None
    fecha_presentacion: Optional[date] = None


class PeriodoFiscal(PeriodoFiscalBase, table=True):
    __tablename__ = "periodos_fiscales"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)


class PeriodoFiscalCrear(SQLModel):
    anio_gravable: int = Field(ge=2000, le=2100)


class PeriodoFiscalActualizar(SQLModel):
    fecha_vencimiento_manual: Optional[date] = None
    fecha_presentacion: Optional[date] = None


class PeriodoFiscalLeer(PeriodoFiscalBase):
    id: int
    contribuyente_id: int
