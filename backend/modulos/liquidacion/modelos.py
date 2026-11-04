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


class CategoriaDepreciacion(str, Enum):
    """Categorías de la tabla del art. 137 ET.

    Es un enum y no texto libre porque cada categoría lleva su tasa máxima
    asociada: un valor fuera de la tabla no tiene tasa y el activo quedaría sin
    depreciar sin que nadie lo note.
    """

    CONSTRUCCIONES_Y_EDIFICACIONES = "CONSTRUCCIONES_Y_EDIFICACIONES"
    ACUEDUCTO_PLANTA_Y_REDES = "ACUEDUCTO_PLANTA_Y_REDES"
    VIAS_DE_COMUNICACION = "VIAS_DE_COMUNICACION"
    FLOTA_Y_EQUIPO_AEREO = "FLOTA_Y_EQUIPO_AEREO"
    FLOTA_Y_EQUIPO_FERREO = "FLOTA_Y_EQUIPO_FERREO"
    FLOTA_Y_EQUIPO_FLUVIAL = "FLOTA_Y_EQUIPO_FLUVIAL"
    ARMAMENTO_Y_EQUIPO_DE_VIGILANCIA = "ARMAMENTO_Y_EQUIPO_DE_VIGILANCIA"
    EQUIPO_ELECTRICO = "EQUIPO_ELECTRICO"
    FLOTA_Y_EQUIPO_DE_TRANSPORTE_TERRESTRE = "FLOTA_Y_EQUIPO_DE_TRANSPORTE_TERRESTRE"
    MAQUINARIA_Y_EQUIPOS = "MAQUINARIA_Y_EQUIPOS"
    MUEBLES_Y_ENSERES = "MUEBLES_Y_ENSERES"
    EQUIPO_MEDICO_CIENTIFICO = "EQUIPO_MEDICO_CIENTIFICO"
    ENVASES_EMPAQUES_Y_HERRAMIENTAS = "ENVASES_EMPAQUES_Y_HERRAMIENTAS"
    EQUIPO_DE_COMPUTACION = "EQUIPO_DE_COMPUTACION"
    REDES_DE_PROCESAMIENTO_DE_DATOS = "REDES_DE_PROCESAMIENTO_DE_DATOS"
    EQUIPO_DE_COMUNICACION = "EQUIPO_DE_COMUNICACION"


class MetodoAnticipo(str, Enum):
    DIRECTO = "DIRECTO"
    PROMEDIO = "PROMEDIO"
    MENOR = "MENOR"


class TipoRentaPerdida(str, Enum):
    """Tipos de renta que admiten compensación de pérdidas.

    No están las rentas de trabajo con vínculo laboral (art. 156), ni pensiones
    ni dividendos: en esas no se puede generar ni compensar pérdida.
    """

    CAPITAL = "CAPITAL"
    NO_LABORAL = "NO_LABORAL"
    TRABAJO_SIN_VINCULO = "TRABAJO_SIN_VINCULO"


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
    metodo_anticipo: MetodoAnticipo = Field(default=MetodoAnticipo.DIRECTO)
    impuesto_neto_anio_anterior: Decimal = _dinero()

    # Bancarización (art. 771-5). Se capturan los totales del año: la
    # aplicación solo conoce las compras de inventario, no todos los pagos.
    total_pagos_del_anio: Decimal = _dinero()
    pagos_en_efectivo: Decimal = _dinero()

    # Comparación patrimonial (art. 236). El patrimonio del año anterior se
    # deduce de los activos del periodo previo; este campo solo lo sobrescribe.
    patrimonio_liquido_anterior_manual: Optional[Decimal] = Field(
        default=None, sa_type=Numeric(18, 2)
    )
    impuestos_pagados_en_el_anio: Decimal = _dinero()
    justificaciones_patrimoniales: Decimal = _dinero()
    aceptar_renta_comparacion_patrimonial: bool = Field(default=False)

    # Subcédula a la que se imputa la depreciación.
    cedula_depreciacion: Cedula = Field(default=Cedula.NO_LABORAL)


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
    metodo_anticipo: Optional[MetodoAnticipo] = None
    impuesto_neto_anio_anterior: Optional[Decimal] = Field(default=None, ge=0)
    total_pagos_del_anio: Optional[Decimal] = Field(default=None, ge=0)
    pagos_en_efectivo: Optional[Decimal] = Field(default=None, ge=0)
    patrimonio_liquido_anterior_manual: Optional[Decimal] = Field(default=None, ge=0)
    impuestos_pagados_en_el_anio: Optional[Decimal] = Field(default=None, ge=0)
    justificaciones_patrimoniales: Optional[Decimal] = Field(default=None, ge=0)
    aceptar_renta_comparacion_patrimonial: Optional[bool] = None
    cedula_depreciacion: Optional[Cedula] = None


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


# --- Activos depreciables ---------------------------------------------------


class DatosDepreciacionBase(SQLModel):
    categoria: CategoriaDepreciacion
    vida_util_anios: int = Field(ge=1, le=100)
    valor_residual: Decimal = Field(default=CERO, sa_type=Numeric(18, 2), ge=0)
    depreciacion_acumulada: Decimal = Field(default=CERO, sa_type=Numeric(18, 2), ge=0)
    meses_en_el_periodo: int = Field(default=12, ge=0, le=12)


class DatosDepreciacion(DatosDepreciacionBase, table=True):
    """Datos de depreciación de un activo ya registrado.

    Tabla aparte y no columnas en `activos` por la misma razón que
    `ClasificacionIngreso`: no alterar el esquema de un módulo con pruebas en
    verde cerca de la entrega. Consolidar ambas en sus tablas de origen está en
    el roadmap.
    """

    __tablename__ = "datos_depreciacion"

    activo_id: int = Field(primary_key=True, foreign_key="activos.id")
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)


class DatosDepreciacionGuardar(DatosDepreciacionBase):
    activo_id: int


class DatosDepreciacionLeer(DatosDepreciacionBase):
    activo_id: int
    periodo_fiscal_id: int
    descripcion: str
    costo_fiscal: Decimal
    tasa_maxima_art_137: Decimal
    depreciacion_del_periodo: Decimal
    formula: str


# --- Pérdidas fiscales compensables ----------------------------------------


class PerdidaFiscalBase(SQLModel):
    anio_origen: int = Field(ge=2000, le=2100)
    tipo_renta: TipoRentaPerdida
    valor: Decimal = Field(sa_type=Numeric(18, 2), gt=0)
    valor_compensado: Decimal = Field(default=CERO, sa_type=Numeric(18, 2), ge=0)
    nota: str = Field(default="", max_length=300)


class PerdidaFiscal(PerdidaFiscalBase, table=True):
    """Pérdida de un año anterior pendiente de compensar.

    Se guarda por contribuyente y no por periodo: una pérdida de 2019 se puede
    compensar en cualquiera de los doce años siguientes, así que no pertenece a
    un periodo en particular.
    """

    __tablename__ = "perdidas_fiscales"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)


class PerdidaFiscalCrear(PerdidaFiscalBase):
    pass


class PerdidaFiscalLeer(PerdidaFiscalBase):
    id: int
    contribuyente_id: int
    saldo_por_compensar: Decimal
    vigente: bool


# --- Pagos individuales en efectivo (art. 771-5 par. 2) --------------------


class PagoEfectivoBase(SQLModel):
    descripcion: str = Field(min_length=1, max_length=200)
    valor: Decimal = Field(sa_type=Numeric(18, 2), gt=0)


class PagoEfectivo(PagoEfectivoBase, table=True):
    __tablename__ = "pagos_efectivo"

    id: Optional[int] = Field(default=None, primary_key=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)


class PagoEfectivoCrear(PagoEfectivoBase):
    pass


class PagoEfectivoLeer(PagoEfectivoBase):
    id: int
    periodo_fiscal_id: int
    supera_limite_individual: bool
