"""Modelos de la hoja de liquidación.

La hoja guarda los insumos que el contador aporta y que no se pueden deducir de
la exógena ni del resto de la aplicación: cuántos dependientes tiene el
contribuyente, qué deducciones va a solicitar, si optó por costos y gastos en
honorarios, qué dividendos le certificaron. Son decisiones profesionales, no
datos: por eso se persisten con quién las guardó y cuándo, y no se infieren.

Todos los importes son NUMERIC(18,2) en la base y Decimal en Python. El resto
de la aplicación todavía usa float; la conversión ocurre en `servicios.py`, en
la frontera, y está marcada ahí. Migrar los módulos antiguos a Decimal está en
el roadmap como tarea aparte porque toca los 195 tests existentes.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from sqlalchemy import Numeric
from sqlmodel import Field, SQLModel

CERO = Decimal("0")


def _dinero(**kwargs) -> Field:
    return Field(default=CERO, sa_type=Numeric(18, 2), **kwargs)


class Cedula(str, Enum):
    """Cédula o subcédula a la que pertenece un ingreso.

    SIN_CLASIFICAR es un estado explícito, no un error silencioso: el motor
    excluye esos ingresos de la liquidación y los reporta como diagnóstico para
    que el contador los clasifique. Adivinar la cédula de un ingreso cambia el
    impuesto y no es una decisión que deba tomar el software.
    """

    TRABAJO = "TRABAJO"
    TRABAJO_SIN_VINCULO = "TRABAJO_SIN_VINCULO"
    CAPITAL = "CAPITAL"
    NO_LABORAL = "NO_LABORAL"
    EXCLUIDO = "EXCLUIDO"
    SIN_CLASIFICAR = "SIN_CLASIFICAR"


class HojaLiquidacionBase(SQLModel):
    # Patrimonio. El patrimonio bruto se calcula desde los activos registrados;
    # las deudas no existen como entidad en la aplicación y se capturan aquí.
    deudas: Decimal = _dinero()

    # Cédula general: rentas de trabajo
    aportes_obligatorios_salud: Decimal = _dinero()
    aportes_obligatorios_pension: Decimal = _dinero()
    otros_ingresos_no_constitutivos: Decimal = _dinero()
    opta_por_costos_y_gastos: bool = Field(default=False)
    costos_y_gastos_sin_vinculo_laboral: Decimal = _dinero()

    # Deducciones fuera del límite general
    numero_dependientes: int = Field(default=0, ge=0, le=20)
    compras_con_factura_electronica: Decimal = _dinero()

    # Cédula de pensiones
    ingresos_pensiones: Decimal = _dinero()
    incrngo_pensiones: Decimal = _dinero()
    meses_pension_causados: int = Field(default=12, ge=0, le=12)

    # Dividendos (del certificado de la sociedad)
    dividendos_no_gravados: Decimal = _dinero()
    dividendos_gravados: Decimal = _dinero()
    retencion_dividendos: Decimal = _dinero()

    # Ganancias ocasionales
    go_ingresos: Decimal = _dinero()
    go_costos: Decimal = _dinero()
    go_ganancia_exenta: Decimal = _dinero()
    go_loterias_rifas_apuestas: Decimal = _dinero()
    go_retenciones: Decimal = _dinero()

    # Cierre de la liquidación
    renta_presuntiva: Decimal = _dinero()
    otros_descuentos_tributarios: Decimal = _dinero()
    anticipo_pagado_anio_anterior: Decimal = _dinero()
    saldo_a_favor_anio_anterior: Decimal = _dinero()
    anios_declarando: int = Field(default=3, ge=1, le=99)


class HojaLiquidacion(HojaLiquidacionBase, table=True):
    __tablename__ = "hojas_liquidacion"

    periodo_fiscal_id: int = Field(
        primary_key=True, foreign_key="periodos_fiscales.id"
    )
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    actualizado_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    actualizado_por_contador_id: Optional[int] = Field(
        default=None, foreign_key="contadores.id"
    )


class HojaLiquidacionActualizar(SQLModel):
    """Actualización parcial: solo se escriben los campos enviados."""

    deudas: Optional[Decimal] = Field(default=None, ge=0)
    aportes_obligatorios_salud: Optional[Decimal] = Field(default=None, ge=0)
    aportes_obligatorios_pension: Optional[Decimal] = Field(default=None, ge=0)
    otros_ingresos_no_constitutivos: Optional[Decimal] = Field(default=None, ge=0)
    opta_por_costos_y_gastos: Optional[bool] = None
    costos_y_gastos_sin_vinculo_laboral: Optional[Decimal] = Field(default=None, ge=0)
    numero_dependientes: Optional[int] = Field(default=None, ge=0, le=20)
    compras_con_factura_electronica: Optional[Decimal] = Field(default=None, ge=0)
    ingresos_pensiones: Optional[Decimal] = Field(default=None, ge=0)
    incrngo_pensiones: Optional[Decimal] = Field(default=None, ge=0)
    meses_pension_causados: Optional[int] = Field(default=None, ge=0, le=12)
    dividendos_no_gravados: Optional[Decimal] = Field(default=None, ge=0)
    dividendos_gravados: Optional[Decimal] = Field(default=None, ge=0)
    retencion_dividendos: Optional[Decimal] = Field(default=None, ge=0)
    go_ingresos: Optional[Decimal] = Field(default=None, ge=0)
    go_costos: Optional[Decimal] = Field(default=None, ge=0)
    go_ganancia_exenta: Optional[Decimal] = Field(default=None, ge=0)
    go_loterias_rifas_apuestas: Optional[Decimal] = Field(default=None, ge=0)
    go_retenciones: Optional[Decimal] = Field(default=None, ge=0)
    renta_presuntiva: Optional[Decimal] = Field(default=None, ge=0)
    otros_descuentos_tributarios: Optional[Decimal] = Field(default=None, ge=0)
    anticipo_pagado_anio_anterior: Optional[Decimal] = Field(default=None, ge=0)
    saldo_a_favor_anio_anterior: Optional[Decimal] = Field(default=None, ge=0)
    anios_declarando: Optional[int] = Field(default=None, ge=1, le=99)


class HojaLiquidacionLeer(HojaLiquidacionBase):
    periodo_fiscal_id: int
    contribuyente_id: int
    actualizado_en: datetime


class DeduccionSolicitadaBase(SQLModel):
    nombre: str = Field(min_length=1, max_length=200)
    valor: Decimal = Field(sa_type=Numeric(18, 2), ge=0)
    sujeto_a_limite_general: bool = Field(default=True)
    fuente_legal: str = Field(default="", max_length=200)


class DeduccionSolicitada(DeduccionSolicitadaBase, table=True):
    __tablename__ = "deducciones_solicitadas"

    id: Optional[int] = Field(default=None, primary_key=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)


class DeduccionSolicitadaCrear(DeduccionSolicitadaBase):
    pass


class DeduccionSolicitadaLeer(DeduccionSolicitadaBase):
    id: int
    periodo_fiscal_id: int


class ClasificacionIngreso(SQLModel, table=True):
    """Cédula asignada a una fuente de ingreso.

    Tabla aparte en vez de una columna en `fuentes_ingreso` para no alterar el
    esquema de un módulo con pruebas en verde a tres semanas de la entrega. En
    el roadmap figura unificarla como columna, que es el diseño correcto.
    """

    __tablename__ = "clasificaciones_ingreso"

    fuente_ingreso_id: int = Field(primary_key=True, foreign_key="fuentes_ingreso.id")
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)
    cedula: Cedula


class ClasificacionIngresoDatos(SQLModel):
    fuente_ingreso_id: int
    cedula: Cedula


class IngresoClasificadoLeer(SQLModel):
    fuente_ingreso_id: int
    concepto: str
    valor_anual: Decimal
    retencion_fuente: Decimal
    cedula: Cedula
    origen_clasificacion: str  # MANUAL | SUGERIDA


# --- Esquemas de salida de la liquidación ----------------------------------


class RenglonLeer(SQLModel):
    codigo: str
    nombre: str
    valor: Decimal
    valor_declarable: Decimal
    formula: str
    fuente_legal: str


class ParametrosAplicadosLeer(SQLModel):
    anio_gravable: int
    regimen: str
    uvt: Decimal
    fuente_uvt: str
    fuente_tabla_renta: str
    limite_general_porcentaje: Decimal
    limite_general_tope_uvt: Decimal
    fuente_limite_general: str


class LiquidacionLeer(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    anio_gravable: int
    parametros: ParametrosAplicadosLeer
    renglones: List[RenglonLeer]
    diagnosticos: List[str]
    notas: List[str]
    ingresos_sin_clasificar: List[IngresoClasificadoLeer] = []
    advertencia: str = (
        "Borrador de liquidación generado a partir de los datos registrados. "
        "La responsabilidad de la declaración es del contribuyente y del "
        "contador que la firma (art. 581 ET): revise cada renglón, su fórmula y "
        "su fuente legal antes de transcribirlo. Los números de renglón del "
        "formulario 210 los fija la resolución de la DIAN de cada año."
    )
