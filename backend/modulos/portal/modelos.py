"""Modelos del portal de carga del contribuyente.

Las cuatro piezas que viven aquí
--------------------------------
`EnlaceCarga`        el enlace que el contador genera desde la ficha.
`AutorizacionTratamiento`  la aceptación de la política, con versión y fecha.
`RequerimientoDocumento`   un documento pedido, en lenguaje común.
`DatoAdicional`      lo que la exógena nunca trae y entra por formulario.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from sqlalchemy import DateTime, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _dinero(**kwargs) -> Field:
    return Field(default=Decimal("0"), sa_type=Numeric(18, 2), **kwargs)


# ---------------------------------------------------------------------------
# Enlace de carga
# ---------------------------------------------------------------------------


class EnlaceCarga(SQLModel, table=True):
    """Un enlace de carga con alcance a un contribuyente y un periodo.

    Del token solo se guarda el hash. Si la base de datos se filtra, nadie
    puede reconstruir un enlace válido a partir de ella: para eso serviría el
    token en claro, y no está.

    SHA-256 y no Argon2 a propósito: el token son 256 bits generados por
    `secrets`, no una contraseña elegida por una persona. Contra eso no existe
    ataque de diccionario que haya que encarecer, y un hash rápido permite
    buscar el enlace por igualdad sobre un índice en vez de probar el token
    contra todas las filas de la tabla.

    `prefijo` son los primeros caracteres del token y se guarda en claro: le
    permite al contador distinguir dos enlaces en la pantalla ("…termina en
    4f2a") sin que eso sirva para adivinar el resto.
    """

    __tablename__ = "enlaces_carga"

    id: Optional[int] = Field(default=None, primary_key=True)
    token_hash: str = Field(max_length=64, index=True, unique=True)
    prefijo: str = Field(max_length=8)

    # Alcance. Un enlace sirve para UN contribuyente y UN año gravable: no
    # hay forma de llegar a otro periodo ni a otro cliente del contador.
    contador_id: int = Field(foreign_key="contadores.id", index=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)

    creado_en: datetime = Field(default_factory=_ahora, sa_type=DateTime(timezone=True))
    expira_en: datetime = Field(sa_type=DateTime(timezone=True))
    revocado_en: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    # Reanudable: el enlace no se consume al usarlo. Esto solo registra la
    # última vez que se abrió, para que el contador vea si el cliente entró.
    ultimo_acceso_en: Optional[datetime] = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    nota: Optional[str] = Field(default=None, max_length=200)


class EnlaceCargaCrear(SQLModel):
    periodo_fiscal_id: int
    dias_vigencia: int = Field(default=30, ge=1, le=180)
    nota: Optional[str] = Field(default=None, max_length=200)


class EnlaceCargaLeer(SQLModel):
    """Lo que ve el contador. Nunca incluye el token."""

    id: int
    contribuyente_id: int
    periodo_fiscal_id: int
    anio_gravable: Optional[int] = None
    prefijo: str
    creado_en: datetime
    expira_en: datetime
    revocado_en: Optional[datetime]
    ultimo_acceso_en: Optional[datetime]
    nota: Optional[str]
    vigente: bool
    politica_aceptada: bool = False
    version_politica_aceptada: Optional[str] = None
    politica_aceptada_en: Optional[datetime] = None


class EnlaceCargaCreado(EnlaceCargaLeer):
    """La respuesta de la creación: la única vez que se devuelve el token.

    No se puede volver a consultar. Si el contador lo pierde, genera otro y
    revoca este: es más seguro que poder recuperarlo.
    """

    token: str
    ruta: str


# ---------------------------------------------------------------------------
# Autorización de tratamiento de datos
# ---------------------------------------------------------------------------


class AutorizacionTratamiento(SQLModel, table=True):
    __tablename__ = "autorizaciones_tratamiento"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    enlace_carga_id: int = Field(foreign_key="enlaces_carga.id", index=True)
    # La versión del texto que el titular leyó. Sin esto, «aceptó» no prueba
    # nada: no se sabría qué decía la política ese día.
    version_politica: str = Field(max_length=20)
    aceptada_en: datetime = Field(default_factory=_ahora, sa_type=DateTime(timezone=True))
    nombre_quien_acepta: str = Field(max_length=200)
    documento_quien_acepta: Optional[str] = Field(default=None, max_length=20)
    # Huella de la conexión, como respaldo de la aceptación. La IP es un dato
    # personal, así que se guarda el prefijo de red y no la dirección exacta.
    red_origen: Optional[str] = Field(default=None, max_length=45)
    agente_usuario: Optional[str] = Field(default=None, max_length=300)


class AceptarPolitica(SQLModel):
    version_politica: str = Field(max_length=20)
    nombre_quien_acepta: str = Field(min_length=3, max_length=200)
    documento_quien_acepta: Optional[str] = Field(default=None, max_length=20)
    acepto: bool


class AutorizacionLeer(SQLModel):
    version_politica: str
    aceptada_en: datetime
    nombre_quien_acepta: str
    documento_quien_acepta: Optional[str]


class PoliticaLeer(SQLModel):
    version: str
    vigente_desde: date
    titulo: str
    finalidades: List[str]
    responsable: str
    derechos: str
    texto: str


# ---------------------------------------------------------------------------
# Requerimientos de documento
# ---------------------------------------------------------------------------


class EstadoRequerimiento(str, Enum):
    """Los cuatro estados que el contribuyente puede marcar.

    «Cargado» no está en la lista a propósito: tener un archivo es un hecho
    aparte del estado, no un quinto estado. Se puede haber subido un papel y
    seguir sin entender de qué se trata, y esas dos cosas le dicen al contador
    cosas distintas.
    """

    PENDIENTE = "PENDIENTE"
    NO_APLICA = "NO_APLICA"
    NO_LO_TENGO = "NO_LO_TENGO"
    NO_ENTIENDO = "NO_ENTIENDO"


class OrigenRequerimiento(str, Enum):
    EXOGENA = "EXOGENA"
    ADICIONAL = "ADICIONAL"


class RequerimientoDocumento(SQLModel, table=True):
    """Un documento pedido al contribuyente, en lenguaje común.

    La clave única por (periodo, origen, referencia) hace que volver a cargar
    la exógena sea idempotente: el requerimiento de una fila que ya existía se
    actualiza en su sitio y **conserva el estado y los archivos** que el
    contribuyente ya había puesto. Sin eso, cada corrida nueva del archivo le
    borraría el trabajo hecho.
    """

    __tablename__ = "requerimientos_documento"
    __table_args__ = (
        UniqueConstraint(
            "periodo_fiscal_id",
            "origen",
            "referencia",
            name="uq_requerimiento_origen_referencia",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)

    origen: OrigenRequerimiento = Field(default=OrigenRequerimiento.EXOGENA)
    # Identidad estable de la fila que lo originó, dentro de su origen:
    # el id del RegistroExogena, o el del DatoAdicional.
    referencia: int

    reporte_exogena_id: Optional[int] = Field(
        default=None, foreign_key="reportes_exogena.id", index=True
    )

    titulo: str = Field(max_length=300)
    explicacion: str = Field(max_length=1000)
    nit_reportante: Optional[str] = Field(default=None, max_length=20)
    nombre_reportante: Optional[str] = Field(default=None, max_length=300)
    concepto_code: Optional[str] = Field(default=None, max_length=10)
    detalle_original: Optional[str] = Field(default=None, max_length=500)
    valor_exogena: Optional[float] = None
    categoria_sugerida: str = Field(default="OTRO", max_length=20)

    # False → la aplicación no supo qué documento es. No se descarta: queda
    # marcado para que el contador lo clasifique.
    concepto_reconocido: bool = Field(default=True)
    motivo_revision: Optional[str] = Field(default=None, max_length=300)
    requiere_soporte: bool = Field(default=True)

    estado: EstadoRequerimiento = Field(default=EstadoRequerimiento.PENDIENTE)
    # Opcional a propósito: el estado sí es obligatorio, el valor no. Un
    # contribuyente puede saber que el documento no aplica sin saber la cifra.
    valor_informado: Optional[Decimal] = Field(default=None, sa_type=Numeric(18, 2))
    nota_contribuyente: Optional[str] = Field(default=None, max_length=500)
    revisado_por_contador: bool = Field(default=False)
    actualizado_en: datetime = Field(default_factory=_ahora, sa_type=DateTime(timezone=True))


class RequerimientoActualizar(SQLModel):
    """El estado es obligatorio; el valor y la nota son opcionales."""

    estado: EstadoRequerimiento
    valor_informado: Optional[Decimal] = Field(default=None, ge=0)
    nota_contribuyente: Optional[str] = Field(default=None, max_length=500)


class ArchivoRequerimiento(SQLModel):
    id: int
    nombre_original: str
    tamano_bytes: int
    creado_en: datetime


class RequerimientoLeer(SQLModel):
    id: int
    contribuyente_id: int
    periodo_fiscal_id: int
    origen: OrigenRequerimiento
    titulo: str
    explicacion: str
    nit_reportante: Optional[str]
    nombre_reportante: Optional[str]
    concepto_code: Optional[str]
    detalle_original: Optional[str]
    valor_exogena: Optional[float]
    categoria_sugerida: str
    concepto_reconocido: bool
    motivo_revision: Optional[str]
    requiere_soporte: bool
    estado: EstadoRequerimiento
    valor_informado: Optional[Decimal]
    nota_contribuyente: Optional[str]
    revisado_por_contador: bool
    actualizado_en: datetime
    archivos: List[ArchivoRequerimiento] = []
    resuelto: bool = False


class ResumenRequerimientos(SQLModel):
    """Lo que el panel de cartera necesita para decir «a quién le falta qué»."""

    total: int = 0
    con_soporte: int = 0
    pendientes: int = 0
    no_lo_tengo: int = 0
    no_aplica: int = 0
    no_entiendo: int = 0
    sin_reconocer: int = 0


# ---------------------------------------------------------------------------
# Datos adicionales (lo que la exógena nunca trae)
# ---------------------------------------------------------------------------


class TipoAdicional(str, Enum):
    """Conceptos que la exógena no reporta y nadie puede deducir del archivo.

    Son los que se pierden cuando la declaración se arma solo con la exógena:
    el archivo no sabe cuántos dependientes tiene alguien, ni qué pagó de
    medicina prepagada, ni qué tiene en el exterior.
    """

    DEPENDIENTE = "DEPENDIENTE"
    INTERESES_VIVIENDA = "INTERESES_VIVIENDA"
    MEDICINA_PREPAGADA = "MEDICINA_PREPAGADA"
    AHORRO_AFC = "AHORRO_AFC"
    APORTES_VOLUNTARIOS_PENSION = "APORTES_VOLUNTARIOS_PENSION"
    ACTIVO = "ACTIVO"
    DEUDA = "DEUDA"
    BIEN_EXTERIOR = "BIEN_EXTERIOR"


class DatoAdicional(SQLModel, table=True):
    __tablename__ = "datos_adicionales"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)

    tipo: TipoAdicional
    descripcion: str = Field(max_length=300)
    valor: Decimal = _dinero(ge=0)
    # Solo para dependientes: el número de personas. El tope del art. 336 es
    # por dependiente, así que el dato que importa es cuántos, no un monto.
    cantidad: Optional[int] = Field(default=None, ge=0, le=20)
    pais: Optional[str] = Field(default=None, max_length=60)
    creado_en: datetime = Field(default_factory=_ahora, sa_type=DateTime(timezone=True))
    # Quién lo capturó: el contribuyente desde el enlace, o el contador.
    capturado_en_portal: bool = Field(default=True)


class DatoAdicionalCrear(SQLModel):
    tipo: TipoAdicional
    descripcion: str = Field(min_length=1, max_length=300)
    valor: Decimal = Field(default=Decimal("0"), ge=0)
    cantidad: Optional[int] = Field(default=None, ge=0, le=20)
    pais: Optional[str] = Field(default=None, max_length=60)


class DatoAdicionalLeer(SQLModel):
    id: int
    contribuyente_id: int
    periodo_fiscal_id: int
    tipo: TipoAdicional
    descripcion: str
    valor: Decimal
    cantidad: Optional[int]
    pais: Optional[str]
    creado_en: datetime
    capturado_en_portal: bool


class ParametroAdicional(SQLModel):
    """El tope vigente de un concepto, ya convertido a pesos del año.

    Se expone al formulario para que los límites que el contribuyente ve en
    pantalla sean los mismos que el servidor valida, y los dos salgan de la
    tabla de parámetros del año, no de un número escrito en el código.
    """

    tipo: TipoAdicional
    etiqueta: str
    pide_valor: bool = True
    pide_cantidad: bool = False
    pide_pais: bool = False
    tope_anual_en_pesos: Optional[Decimal] = None
    tope_uvt: Optional[Decimal] = None
    es_tope_mensual: bool = False
    grupo_tope_compartido: Optional[str] = None
    cantidad_maxima: Optional[int] = None
    fuente_legal: Optional[str] = None
    advertencia: Optional[str] = None


class ParametrosAdicionales(SQLModel):
    anio_gravable: int
    uvt: Decimal
    fuente_uvt: str
    conceptos: List[ParametroAdicional]


# ---------------------------------------------------------------------------
# Lo que ve quien abre el enlace
# ---------------------------------------------------------------------------


class SesionPortal(SQLModel):
    """Todo lo que el portal público devuelve. Nada de aquí es la liquidación.

    Lo que el contribuyente puede ver es: de quién es el enlace, qué año se
    está declarando, la política, qué documentos se le piden y qué anotó él
    mismo. No hay un solo campo que venga del motor de liquidación, de la
    conciliación o de la cartera del contador.
    """

    contribuyente_nombre: str
    # Enmascarado: quien abre el enlace confirma que es el suyo sin que una
    # filtración del enlace entregue el documento completo.
    documento_enmascarado: str
    contador_nombre: str
    anio_gravable: int
    expira_en: datetime
    politica: PoliticaLeer
    autorizacion: Optional[AutorizacionLeer] = None
    exogena_cargada: bool = False
    fecha_corte_exogena: Optional[date] = None
    version_exogena: Optional[int] = None
    requerimientos: List[RequerimientoLeer] = []
    adicionales: List[DatoAdicionalLeer] = []
    resumen: ResumenRequerimientos = ResumenRequerimientos()


class ResultadoCargaExogena(SQLModel):
    reporte_exogena_id: int
    version: int
    fecha_corte: Optional[date]
    cantidad_registros: int
    requerimientos_creados: int
    requerimientos_actualizados: int
    sin_reconocer: int
    errores_en_filas: int
