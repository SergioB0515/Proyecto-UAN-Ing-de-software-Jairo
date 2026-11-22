"""Modelos de la hoja de liquidación: insumos que aporta el contador.

Importes en NUMERIC(18,2) / Decimal.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from sqlalchemy import Numeric
from sqlmodel import Field, SQLModel

CERO = Decimal("0")


def _dinero(**kwargs) -> Field:
    return Field(default=CERO, sa_type=Numeric(18, 2), **kwargs)


class CategoriaDepreciacion(str, Enum):
    """Categorías del art. 137 ET. Enum: cada una tiene su tasa máxima."""

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


class ReduccionSancion(str, Enum):
    """Reducción del art. 640 ET."""

    NINGUNA = "NINGUNA"
    AL_75 = "AL_75"  # sin la conducta en el último año
    AL_50 = "AL_50"  # sin la conducta en los dos últimos años


class TipoRentaPerdida(str, Enum):
    """Rentas que admiten compensación de pérdidas. Excluye trabajo con vínculo
    (art. 156), pensiones y dividendos.
    """

    CAPITAL = "CAPITAL"
    NO_LABORAL = "NO_LABORAL"
    TRABAJO_SIN_VINCULO = "TRABAJO_SIN_VINCULO"


class Cedula(str, Enum):
    """Cédula de un ingreso. SIN_CLASIFICAR se excluye de la liquidación y se reporta."""

    TRABAJO = "TRABAJO"
    TRABAJO_SIN_VINCULO = "TRABAJO_SIN_VINCULO"
    CAPITAL = "CAPITAL"
    NO_LABORAL = "NO_LABORAL"
    EXCLUIDO = "EXCLUIDO"
    SIN_CLASIFICAR = "SIN_CLASIFICAR"


class HojaLiquidacionBase(SQLModel):
    # Patrimonio. Bruto desde activos; deudas se capturan aquí.
    deudas: Decimal = _dinero()

    # Rentas de trabajo
    aportes_obligatorios_salud: Decimal = _dinero()
    aportes_obligatorios_pension: Decimal = _dinero()
    otros_ingresos_no_constitutivos: Decimal = _dinero()
    opta_por_costos_y_gastos: bool = Field(default=False)
    costos_y_gastos_sin_vinculo_laboral: Decimal = _dinero()

    # Rentas de capital y no laborales: costos y gastos distintos de kardex y
    # depreciación, y devoluciones.
    ingresos_no_constitutivos_capital: Decimal = _dinero()
    costos_y_gastos_capital: Decimal = _dinero()
    ingresos_no_constitutivos_no_laborales: Decimal = _dinero()
    devoluciones_no_laborales: Decimal = _dinero()
    costos_y_gastos_no_laborales: Decimal = _dinero()

    # Fuera del límite general
    numero_dependientes: int = Field(default=0, ge=0, le=20)
    compras_con_factura_electronica: Decimal = _dinero()

    # Pensiones
    ingresos_pensiones: Decimal = _dinero()
    incrngo_pensiones: Decimal = _dinero()
    meses_pension_causados: int = Field(default=12, ge=0, le=12)

    # Dividendos (certificado de la sociedad)
    dividendos_no_gravados: Decimal = _dinero()
    dividendos_gravados: Decimal = _dinero()
    retencion_dividendos: Decimal = _dinero()

    # Ganancias ocasionales
    go_ingresos: Decimal = _dinero()
    go_costos: Decimal = _dinero()
    go_ganancia_exenta: Decimal = _dinero()
    go_loterias_rifas_apuestas: Decimal = _dinero()
    go_retenciones: Decimal = _dinero()

    # Cierre
    renta_presuntiva: Decimal = _dinero()
    otros_descuentos_tributarios: Decimal = _dinero()
    anticipo_pagado_anio_anterior: Decimal = _dinero()
    saldo_a_favor_anio_anterior: Decimal = _dinero()
    anios_declarando: int = Field(default=3, ge=1, le=99)
    metodo_anticipo: MetodoAnticipo = Field(default=MetodoAnticipo.DIRECTO)
    reduccion_sancion: ReduccionSancion = Field(default=ReduccionSancion.NINGUNA)
    impuesto_neto_anio_anterior: Decimal = _dinero()

    # Bancarización (art. 771-5): totales del año.
    total_pagos_del_anio: Decimal = _dinero()
    pagos_en_efectivo: Decimal = _dinero()

    # Comparación patrimonial (art. 236). Sobrescribe el patrimonio calculado.
    patrimonio_liquido_anterior_manual: Optional[Decimal] = Field(
        default=None, sa_type=Numeric(18, 2)
    )
    impuestos_pagados_en_el_anio: Decimal = _dinero()
    justificaciones_patrimoniales: Decimal = _dinero()
    aceptar_renta_comparacion_patrimonial: bool = Field(default=False)

    # Subcédula de la depreciación.
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
    """Actualización parcial."""

    deudas: Optional[Decimal] = Field(default=None, ge=0)
    aportes_obligatorios_salud: Optional[Decimal] = Field(default=None, ge=0)
    aportes_obligatorios_pension: Optional[Decimal] = Field(default=None, ge=0)
    otros_ingresos_no_constitutivos: Optional[Decimal] = Field(default=None, ge=0)
    opta_por_costos_y_gastos: Optional[bool] = None
    costos_y_gastos_sin_vinculo_laboral: Optional[Decimal] = Field(default=None, ge=0)
    ingresos_no_constitutivos_capital: Optional[Decimal] = Field(default=None, ge=0)
    costos_y_gastos_capital: Optional[Decimal] = Field(default=None, ge=0)
    ingresos_no_constitutivos_no_laborales: Optional[Decimal] = Field(default=None, ge=0)
    devoluciones_no_laborales: Optional[Decimal] = Field(default=None, ge=0)
    costos_y_gastos_no_laborales: Optional[Decimal] = Field(default=None, ge=0)
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
    reduccion_sancion: Optional[ReduccionSancion] = None
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
    # Concepto del catálogo; define el tope propio.
    codigo_plantilla: Optional[str] = Field(default=None, max_length=60)
    # Columna: TRABAJO, TRABAJO_SIN_VINCULO, CAPITAL o NO_LABORAL. Vacío: la
    # imputa el motor.
    subcedula: Optional[str] = Field(default=None, max_length=30)
    # Fila: EXENTA_AFC, EXENTA_OTRA, DEDUCCION_VIVIENDA o DEDUCCION_OTRA.
    fila_formulario: Optional[str] = Field(default=None, max_length=30)


class DeduccionSolicitada(DeduccionSolicitadaBase, table=True):
    __tablename__ = "deducciones_solicitadas"

    id: Optional[int] = Field(default=None, primary_key=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)


class DeduccionSolicitadaCrear(DeduccionSolicitadaBase):
    pass


class SubcedulaFormulario(str, Enum):
    TRABAJO = "TRABAJO"
    TRABAJO_SIN_VINCULO = "TRABAJO_SIN_VINCULO"
    CAPITAL = "CAPITAL"
    NO_LABORAL = "NO_LABORAL"


class FilaFormulario(str, Enum):
    EXENTA_AFC = "EXENTA_AFC"
    EXENTA_OTRA = "EXENTA_OTRA"
    DEDUCCION_VIVIENDA = "DEDUCCION_VIVIENDA"
    DEDUCCION_OTRA = "DEDUCCION_OTRA"


class DeduccionImputacion(SQLModel):
    """Columna y fila del 210 de una deducción. subcedula nula: la imputa el motor."""

    subcedula: Optional[SubcedulaFormulario] = None
    fila_formulario: FilaFormulario


class DeduccionSolicitadaLeer(DeduccionSolicitadaBase):
    id: int
    periodo_fiscal_id: int


class ClasificacionIngreso(SQLModel, table=True):
    """Cédula asignada a mano a una fuente de ingreso.

    Por qué sigue siendo una tabla aparte y no una columna de
    `fuentes_ingreso`, que es lo que decía una nota anterior:

    La cédula es un concepto de este módulo. `fuentes_ingreso` pertenece a
    `contribuyentes`, que hoy no depende de `liquidacion`: la dependencia va
    en el otro sentido. Ponerle ahí una columna tipada con `Cedula` haría que
    el módulo de abajo hable el vocabulario del de arriba, y la única forma
    de evitarlo sería mover el enum a un sitio compartido, donde tampoco
    corresponde: es vocabulario tributario, no infraestructura.

    Lo que se ganaría a cambio es ahorrarse un join. No alcanza.

    La ausencia de fila significa «sin clasificar a mano»: la cédula la
    sugiere el motor. Por eso solo hay filas para lo que el contador decidió.
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


# Salida de la liquidación


class RenglonLeer(SQLModel):
    codigo: str
    nombre: str
    valor: Decimal
    valor_declarable: Decimal
    formula: str
    fuente_legal: str
    casilla: Optional[int] = None


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
    casillas_marcadas: List[int] = []
    ingresos_sin_clasificar: List[IngresoClasificadoLeer] = []
    advertencia: str = (
        "Borrador de liquidación generado a partir de los datos registrados. "
        "La responsabilidad de la declaración es del contribuyente y del "
        "contador que la firma (art. 581 ET): revise cada renglón, su fórmula y "
        "su fuente legal antes de transcribirlo."
    )


# Escenarios


class CifrasEscenario(SQLModel):
    impuesto: Decimal
    anticipo: Decimal
    saldo_a_pagar: Decimal
    saldo_a_favor: Decimal


class EscenarioLeer(SQLModel):
    """Liquidación con una decisión cambiada."""

    clave: str
    titulo: str
    opcion_actual: str
    opcion_alterna: str
    actual: CifrasEscenario
    alterna: CifrasEscenario
    # Positivo: la alternativa cuesta menos.
    ahorro_en_impuesto: Decimal
    ahorro_en_saldo: Decimal
    explicacion: str


class EscenariosLeer(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    anio_gravable: int
    escenarios: List[EscenarioLeer]
    advertencia: str = (
        "Cada escenario vuelve a liquidar con una sola decisión cambiada y todo lo "
        "demás igual. Son cálculos, no recomendaciones: que una opción dé menos "
        "impuesto no dice si el contribuyente cumple los requisitos para tomarla ni "
        "si tiene los soportes. Las sanciones no entran en la comparación."
    )


# Activos depreciables


class DatosDepreciacionBase(SQLModel):
    categoria: CategoriaDepreciacion
    vida_util_anios: int = Field(ge=1, le=100)
    valor_residual: Decimal = Field(default=CERO, sa_type=Numeric(18, 2), ge=0)
    depreciacion_acumulada: Decimal = Field(default=CERO, sa_type=Numeric(18, 2), ge=0)
    meses_en_el_periodo: int = Field(default=12, ge=0, le=12)


class DatosDepreciacion(DatosDepreciacionBase, table=True):
    """Depreciación de un activo registrado.

    Tampoco pasa a columnas de `activos`, contra lo que decía una nota
    anterior. Solo se deprecian los activos fijos de un negocio: los de un
    asalariado —una cuenta, un carro, un apartamento— no. Serían cinco
    columnas en todas las filas de activos, nulas casi siempre, a cambio de
    ahorrarse un join. Un grupo de atributos opcional y disperso es
    justamente el caso en que una tabla aparte está bien.
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


# Pérdidas fiscales


class PerdidaFiscalBase(SQLModel):
    anio_origen: int = Field(ge=2000, le=2100)
    tipo_renta: TipoRentaPerdida
    valor: Decimal = Field(sa_type=Numeric(18, 2), gt=0)
    valor_compensado: Decimal = Field(default=CERO, sa_type=Numeric(18, 2), ge=0)
    nota: str = Field(default="", max_length=300)


class PerdidaFiscal(PerdidaFiscalBase, table=True):
    """Pérdida pendiente de compensar. Por contribuyente: aplica a varios periodos."""

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


# Pagos en efectivo (art. 771-5 par. 2)


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



# Venta de inmuebles


class TipoInmueble(str, Enum):
    URBANO = "URBANO"
    RURAL_AGROPECUARIO = "RURAL_AGROPECUARIO"
    RURAL = "RURAL"


class VentaInmuebleBase(SQLModel):
    descripcion: str = Field(min_length=3, max_length=300)
    tipo: TipoInmueble = Field(default=TipoInmueble.URBANO)
    fecha_adquisicion: date
    fecha_venta: date
    valor_venta: Decimal = _dinero(ge=0)
    costo_adquisicion: Decimal = _dinero(ge=0)
    mejoras_y_valorizacion: Decimal = _dinero(ge=0)
    # Avalúo del año anterior a la venta (art. 72 ET).
    avaluo_catastral_anterior: Optional[Decimal] = Field(
        default=None, sa_type=Numeric(18, 2), ge=0)
    es_casa_de_habitacion: bool = Field(default=False)
    porcentaje_participacion: Decimal = Field(
        default=Decimal("100"), sa_type=Numeric(5, 2), gt=0, le=100)
    retencion: Decimal = _dinero(ge=0)
    # Factor del art. 73 manual, para años sin tabla.
    factor_manual: Optional[Decimal] = Field(default=None, sa_type=Numeric(12, 4), gt=0)


class VentaInmueble(VentaInmuebleBase, table=True):
    __tablename__ = "ventas_inmuebles"

    id: Optional[int] = Field(default=None, primary_key=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)


class VentaInmuebleCrear(VentaInmuebleBase):
    pass


class VentaInmuebleLeer(VentaInmuebleBase):
    id: int
    periodo_fiscal_id: int
    es_ganancia_ocasional: bool
    factor: Optional[Decimal]
    costo_reajustado: Optional[Decimal]
    costo_fiscal: Decimal
    metodo_costo: str
    utilidad: Decimal
    perdida: Decimal
    exenta: Decimal
    formula: str
    avisos: List[str] = []
