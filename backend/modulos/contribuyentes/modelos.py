"""Contribuyente, Activo y FuenteIngreso. Ver documentacion/07-diagrama-clases.md
y documentacion/03-logica-proyecto.md (Procesos 2 y 3).
"""
from datetime import datetime, timezone
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
    INVENTARIO = "INVENTARIO"  # lo asigna el cierre de periodo (Incremento 5)


# ---------------------------------------------------------------- Contribuyente


class ContribuyenteBase(SQLModel):
    nombre: str = Field(min_length=1, max_length=200)
    rut: str = Field(index=True, max_length=20)
    tipo_contribuyente: TipoContribuyente
    regimen_tributario: str = Field(default="Ordinario", max_length=60)


class Contribuyente(ContribuyenteBase, table=True):
    __tablename__ = "contribuyentes"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Aislamiento por contador (documentacion/04-arquitectura.md): todo
    # acceso a un Contribuyente filtra por esta columna, no solo la UI.
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
    """Todos los campos opcionales: solo se cambia lo que venga."""

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
    # Periodo sobre el que se calculó; None si el contribuyente aún no
    # tiene periodos fiscales (patrimonio 0).
    periodo_fiscal_id: Optional[int] = None
    anio_gravable: Optional[int] = None


# ----------------------------------------------------------------------- Activo


class ActivoBase(SQLModel):
    # HU-03/HU-04: el patrimonio se declara a 31 de diciembre de cada año
    # gravable, así que cada activo pertenece a un periodo fiscal.
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)
    descripcion: str = Field(min_length=1, max_length=200)
    tipo: TipoActivo
    valor: float = Field(gt=0)
    # Vínculo DIAN opcional (documentacion/03-logica-proyecto.md, Proceso 3):
    # lo usa el motor de conciliación del Incremento 3, no este incremento.
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
    """Campos editables de un activo. El periodo no se cambia: un activo
    mal ubicado se elimina y se registra en el año correcto. Un vínculo
    DIAN enviado como null o cadena vacía se borra."""

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
    # Sin gt=0: el Activo INVENTARIO de un cierre puede valer 0 si el
    # negocio cerró el año sin mercancía.
    valor: float


# ------------------------------------------------------------- FuenteIngreso


class FuenteIngresoBase(SQLModel):
    # HU-03: cada fuente de ingreso queda asociada a un periodo fiscal.
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
    """Campos editables de una fuente de ingreso (el periodo no cambia)."""

    concepto: Optional[str] = Field(default=None, min_length=1, max_length=200)
    valor_anual: Optional[float] = Field(default=None, gt=0)
    retencion_fuente: Optional[float] = Field(default=None, ge=0)
    vinculo_codigo_concepto: Optional[str] = Field(default=None, max_length=10)
    vinculo_palabra_clave: Optional[str] = Field(default=None, max_length=200)


class FuenteIngresoLeer(FuenteIngresoBase):
    id: int
    contribuyente_id: int


# -------------------------------------------------------------- PeriodoFiscal
# Nuevo en el Incremento 2: ReporteExogena (modulos/exogena) necesita un
# PeriodoFiscal al que asociarse (documentacion/03-logica-proyecto.md,
# Proceso 4). Vive aquí porque es una propiedad del Contribuyente, igual que
# Activo y FuenteIngreso.


class EstadoPeriodo(str, Enum):
    ABIERTO = "ABIERTO"
    CERRADO = "CERRADO"  # lo asigna el cierre de periodo (Incremento 5)


class PeriodoFiscalBase(SQLModel):
    anio_gravable: int = Field(ge=2000, le=2100)
    estado: EstadoPeriodo = Field(default=EstadoPeriodo.ABIERTO)


class PeriodoFiscal(PeriodoFiscalBase, table=True):
    __tablename__ = "periodos_fiscales"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)


class PeriodoFiscalCrear(SQLModel):
    """Un periodo siempre nace ABIERTO: el estado solo lo cambia el cierre
    de periodo (Incremento 5), nunca el cliente al crearlo."""

    anio_gravable: int = Field(ge=2000, le=2100)


class PeriodoFiscalLeer(PeriodoFiscalBase):
    id: int
    contribuyente_id: int
