from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

from sqlalchemy import DateTime, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel


class OrigenItemConciliacion(str, Enum):
    ACTIVO = "Activo"
    FUENTE_INGRESO = "FuenteIngreso"
    VENTA_INMUEBLE = "VentaInmueble"
    EXOGENA = "Exógena"
    # Lo que la exógena nunca trae y entró por el formulario de adicionales:
    # dependientes, intereses de vivienda, medicina prepagada, AFC/AVP,
    # activos, deudas y bienes del exterior. Aterriza en esta misma tabla,
    # porque tener dos bandejas distintas de «lo que hay» es justo la forma de
    # que algo se quede por fuera de la declaración.
    ADICIONAL = "Adicional"


class EstadoConciliacion(str, Enum):
    """Los cuatro estados de la tabla única de conciliación.

    Los nombres técnicos y lo que significan en palabras:

    COINCIDE                  → coincide
    DISCREPANCIA              → hay diferencia
    NO_DECLARADO              → solo está en la exógena
    NO_REPORTADO_POR_TERCERO  → solo está en lo declarado

    Son cuatro y no cinco a propósito: todo valor, venga del archivo de la
    DIAN, de lo que el contador registró o del formulario de adicionales, cae
    en uno de estos cuatro casos. No hay un «otros» donde esconder lo que no
    se supo clasificar.
    """

    COINCIDE = "COINCIDE"
    DISCREPANCIA = "DISCREPANCIA"
    NO_DECLARADO = "NO_DECLARADO"
    NO_REPORTADO_POR_TERCERO = "NO_REPORTADO_POR_TERCERO"


ETIQUETAS_ESTADO = {
    EstadoConciliacion.COINCIDE: "Coincide",
    EstadoConciliacion.DISCREPANCIA: "Hay diferencia",
    EstadoConciliacion.NO_DECLARADO: "Solo en la exógena",
    EstadoConciliacion.NO_REPORTADO_POR_TERCERO: "Solo en lo declarado",
}


class FuenteValorFinal(str, Enum):
    """De dónde salió el valor que el contador decidió declarar.

    Guardar la fuente y no solo la cifra es lo que hace auditable la
    decisión. Frente a un requerimiento de la DIAN la pregunta no es «cuánto
    declaró» —eso está en el formulario— sino «por qué ese número y no el que
    reportó el tercero». Sin este campo la respuesta sería la memoria del
    contador.
    """

    EXOGENA = "EXOGENA"
    DECLARADO = "DECLARADO"
    MANUAL = "MANUAL"


class DecisionRenglon(SQLModel, table=True):
    """El valor final que el contador fijó para un renglón de la conciliación.

    La clave es (periodo, clave_item): una decisión por fila de la tabla. La
    fila se identifica por lo declarado cuando existe, y por el registro de
    la exógena cuando solo está ahí, así que la decisión sobrevive a que se
    cargue una versión nueva del archivo.
    """

    __tablename__ = "decisiones_renglon"
    __table_args__ = (
        UniqueConstraint("periodo_fiscal_id", "clave_item", name="uq_decision_renglon"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)
    clave_item: str = Field(max_length=60, index=True)

    valor_final: Decimal = Field(sa_type=Numeric(18, 2))
    fuente_elegida: FuenteValorFinal
    nota: Optional[str] = Field(default=None, max_length=500)

    # Quién la tomó y cuándo. Solo el contador fija valores finales, así que
    # este campo nunca queda vacío ni apunta a un contribuyente.
    decidida_por_contador_id: int = Field(foreign_key="contadores.id")
    decidida_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class DecisionRenglonFijar(SQLModel):
    clave_item: str = Field(min_length=1, max_length=60)
    fuente_elegida: FuenteValorFinal
    # Solo se usa con fuente MANUAL. Con EXOGENA o DECLARADO el valor se toma
    # de la fila, no de lo que mande el cliente: si se aceptara, el registro
    # podría decir «elegí el valor de la exógena» y guardar otro número.
    valor_final: Optional[Decimal] = Field(default=None, ge=0)
    nota: Optional[str] = Field(default=None, max_length=500)


class DecisionRenglonLeer(SQLModel):
    clave_item: str
    valor_final: Decimal
    fuente_elegida: FuenteValorFinal
    nota: Optional[str]
    decidida_por_contador_id: int
    decidida_en: datetime


class ItemConciliacion(SQLModel):
    # Identidad estable de la fila, para colgarle la decisión del contador.
    clave: str
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
    etiqueta_estado: Optional[str] = None
    # La decisión del contador, si ya la tomó.
    valor_final: Optional[float] = None
    fuente_valor_final: Optional[FuenteValorFinal] = None
    nota_decision: Optional[str] = None
    decidida_en: Optional[datetime] = None


class ResultadoConciliacion(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    reporte_exogena_id: int
    items: List[ItemConciliacion]
    resumen: Dict[EstadoConciliacion, int]
    total_decididos: int = 0
    total_sin_decidir: int = 0


class RenglonSugerido(SQLModel):
    renglon: str
    valor_total: float
    cantidad_registros: int
    casilla: Optional[int] = None
    nombre_oficial: Optional[str] = None


class RegistroSinAsignar(SQLModel):
    """Valor sin renglón asignado por la DIAN. Lo asigna el contador; no se suma."""

    detalle: str
    valor: float
    renglones_posibles: List[str]
    uso_sugerido: Optional[str] = None


class CuadreTope(SQLModel):
    """Topes del archivo frente al borrador."""

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


# Cruce liquidación / exógena


class DetalleTopeLeer(SQLModel):
    detalle: str
    reportante: str = ""
    valor: Decimal
    valor_propio: Decimal
    participacion: Decimal


class TopeCruzado(SQLModel):
    """Tope reconstruido desde el detalle."""

    numero: int
    nombre: str
    etiqueta: str
    valor_tope: Decimal
    suma_detalle: Decimal
    piso: Optional[Decimal] = None
    valor_esperado: Decimal
    cuadra: bool
    umbral: Optional[Decimal] = None
    supera_umbral: Optional[bool] = None
    registros: List[DetalleTopeLeer] = []
    explicacion: str = ""


class ComparacionCruce(SQLModel):
    clave: str
    titulo: str
    casillas: str
    valor_dian: Optional[Decimal] = None
    valor_declarado: Decimal
    diferencia: Optional[Decimal] = None
    severidad: str
    mensaje: str


class RegistroPendiente(SQLModel):
    detalle: str
    valor: Decimal
    renglones_posibles: List[str] = []
    uso_sugerido: Optional[str] = None


class CruceDian(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    anio_gravable: int
    reporte_exogena_id: int
    obligado_a_declarar: Optional[bool] = None
    topes: List[TopeCruzado]
    comparaciones: List[ComparacionCruce]
    pendientes: List[RegistroPendiente] = []
    informativos: List[RegistroPendiente] = []
    resumen: Dict[str, int] = {}
    diagnosticos: List[str] = []
    advertencia: str = (
        "El cruce compara el borrador de liquidación con lo que terceros le "
        "reportaron a la DIAN en la exógena. La exógena no es completa ni "
        "infalible: un tercero puede reportar mal o no reportar. Una diferencia "
        "es una pregunta que hay que poder responder, no necesariamente un error."
    )
