"""Modelos de gestión: etapas, documentos, declaraciones presentadas, tasas."""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

from sqlalchemy import JSON, Column, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel


# Tablas


class SeguimientoDeclaracion(SQLModel, table=True):
    """Hitos que marca el contador o el cliente. Los calculables no se guardan."""

    __tablename__ = "seguimientos_declaracion"

    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", primary_key=True)
    cruce_revisado_en: Optional[date] = None
    liquidacion_revisada_en: Optional[date] = None
    aprobada_cliente_en: Optional[date] = None
    pagada_en: Optional[date] = None
    valor_pagado: Optional[Decimal] = Field(default=None, sa_type=Numeric(18, 2))
    solicitud_devolucion_en: Optional[date] = None
    # Con emplazamiento notificado la sanción es 20 %, no 10 % (art. 644).
    emplazamiento_notificado: bool = Field(default=False)
    notas: str = Field(default="", max_length=2000)


class EstadoDocumento(str, Enum):
    PENDIENTE = "PENDIENTE"
    RECIBIDO = "RECIBIDO"
    NO_APLICA = "NO_APLICA"


class DocumentoSolicitado(SQLModel, table=True):
    """Decisión del contador sobre un documento (recibido, no aplica) o uno manual."""

    __tablename__ = "documentos_solicitados"
    __table_args__ = (UniqueConstraint("periodo_fiscal_id", "clave"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)
    clave: str = Field(max_length=120)
    descripcion: str = Field(default="", max_length=300)
    tercero: str = Field(default="", max_length=300)
    nit: str = Field(default="", max_length=20)
    motivo: str = Field(default="", max_length=500)
    estado: EstadoDocumento = Field(default=EstadoDocumento.PENDIENTE)
    actualizado_en: Optional[date] = None
    manual: bool = Field(default=False)
    nota: str = Field(default="", max_length=500)


class DeclaracionPresentada(SQLModel, table=True):
    """Declaración presentada, casilla por casilla (APP o MANUAL)."""

    __tablename__ = "declaraciones_presentadas"

    id: Optional[int] = Field(default=None, primary_key=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)
    fecha_presentacion: date
    numero_formulario: Optional[str] = Field(default=None, max_length=30)
    es_correccion: bool = Field(default=False)
    origen: str = Field(default="APP", max_length=10)  # APP | MANUAL
    # Casilla -> valor como texto, sin perder precisión.
    casillas: Dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    registrada_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TasaInteresMoratorio(SQLModel, table=True):
    """Tasa de interés moratorio de un mes (art. 635), % efectivo anual."""

    __tablename__ = "tasas_interes_moratorio"

    anio: int = Field(primary_key=True, ge=2000, le=2100)
    mes: int = Field(primary_key=True, ge=1, le=12)
    tasa_efectiva_anual: Decimal = Field(sa_type=Numeric(7, 4))
    fuente: str = Field(default="", max_length=300)


# Entradas


class SeguimientoActualizar(SQLModel):
    cruce_revisado_en: Optional[date] = None
    liquidacion_revisada_en: Optional[date] = None
    aprobada_cliente_en: Optional[date] = None
    pagada_en: Optional[date] = None
    valor_pagado: Optional[Decimal] = None
    solicitud_devolucion_en: Optional[date] = None
    emplazamiento_notificado: Optional[bool] = None
    notas: Optional[str] = Field(default=None, max_length=2000)


class DocumentoActualizar(SQLModel):
    estado: Optional[EstadoDocumento] = None
    nota: Optional[str] = Field(default=None, max_length=500)


class DocumentoCrear(SQLModel):
    descripcion: str = Field(min_length=3, max_length=300)
    tercero: str = Field(default="", max_length=300)
    motivo: str = Field(default="", max_length=500)


class PresentacionRegistrar(SQLModel):
    fecha_presentacion: date
    numero_formulario: Optional[str] = Field(default=None, max_length=30)


class DeclaracionAnteriorRegistrar(SQLModel):
    anio_gravable: int = Field(ge=2000, le=2100)
    fecha_presentacion: date
    numero_formulario: Optional[str] = Field(default=None, max_length=30)
    casillas: Dict[int, Decimal]


class TasaInteresDatos(SQLModel):
    anio: int = Field(ge=2000, le=2100)
    mes: int = Field(ge=1, le=12)
    tasa_efectiva_anual: Decimal = Field(gt=0, lt=100)
    fuente: str = Field(default="", max_length=300)


# Salidas


class EtapaLeer(SQLModel):
    clave: str
    nombre: str
    # Acción de la etapa pendiente.
    accion: str = ""
    hecha: bool
    automatica: bool
    fecha: Optional[date] = None
    detalle: str = ""


class ProcesoLeer(SQLModel):
    etapas: List[EtapaLeer]
    etapa_actual: Optional[str]
    hechas: int
    total: int
    documentos_pendientes: int = 0


class DocumentoLeer(SQLModel):
    id: Optional[int] = None
    clave: str
    descripcion: str
    tercero: str = ""
    nit: str = ""
    motivo: str = ""
    estado: EstadoDocumento = EstadoDocumento.PENDIENTE
    actualizado_en: Optional[date] = None
    manual: bool = False
    nota: str = ""


class SolicitudDocumentosLeer(SQLModel):
    documentos: List[DocumentoLeer]
    pendientes: int
    recibidos: int
    mensaje: str


class DeclaracionPresentadaLeer(SQLModel):
    id: int
    anio_gravable: int
    fecha_presentacion: date
    numero_formulario: Optional[str]
    es_correccion: bool
    origen: str
    casillas: Dict[int, Decimal]


class CondicionLeer(SQLModel):
    descripcion: str
    cumple: Optional[bool]
    detalle: str = ""


class BeneficioLeer(SQLModel):
    vigente: bool
    meses: Optional[int]
    incremento_porcentaje: Optional[Decimal]
    impuesto_actual: Decimal
    impuesto_anterior: Optional[Decimal]
    impuesto_para_12_meses: Optional[Decimal]
    impuesto_para_6_meses: Optional[Decimal]
    condiciones: List[CondicionLeer]
    conclusion: str
    fuente: str


class FirmezaLeer(SQLModel):
    fecha: Optional[date]
    regla: str
    fuente: str
    notas: List[str] = []


class TramoInteresLeer(SQLModel):
    desde: date
    hasta: date
    dias: int
    tasa_efectiva_anual: Decimal
    interes: Decimal


class InteresesLeer(SQLModel):
    capital: Decimal
    fecha_pago: date
    pagado: bool
    valor: Decimal
    dias: int
    tramos: List[TramoInteresLeer]
    meses_sin_tasa: List[str]
    formula: str
    fuente: str


class CorreccionLeer(SQLModel):
    tipo: str
    mayor_valor: Decimal
    sancion: Decimal
    plazo: Optional[date]
    vencida: Optional[bool]
    formula: str
    fuente: str
    notas: List[str]
    intereses: Optional[InteresesLeer] = None
    total_a_pagar: Decimal


class FilaComparativoLeer(SQLModel):
    casilla: int
    nombre: str
    anterior: Optional[Decimal]
    actual: Optional[Decimal]
    diferencia: Optional[Decimal]
    variacion_porcentaje: Optional[Decimal]
    revisar: bool


class CoherenciaLeer(SQLModel):
    descripcion: str
    esperado: Decimal
    registrado: Decimal
    cuadra: bool
    explicacion: str


class ComparativoLeer(SQLModel):
    anio_anterior: int
    origen_anterior: str
    filas: List[FilaComparativoLeer]
    coherencias: List[CoherenciaLeer]


class GestionLeer(SQLModel):
    anio_gravable: int
    vencimiento: Optional[date]
    fecha_presentacion: Optional[date]
    saldo_a_pagar: Decimal
    saldo_a_favor: Decimal
    proceso: ProcesoLeer
    seguimiento: SeguimientoActualizar
    presentaciones: List[DeclaracionPresentadaLeer]
    declaracion_anterior: Optional[DeclaracionPresentadaLeer]
    comparativo: Optional[ComparativoLeer]
    beneficio_auditoria: BeneficioLeer
    firmeza: FirmezaLeer
    correccion: Optional[CorreccionLeer]
    intereses: Optional[InteresesLeer]
    avisos: List[str] = []
