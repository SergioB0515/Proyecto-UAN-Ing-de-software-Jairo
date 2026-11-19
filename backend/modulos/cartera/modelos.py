from datetime import date
from enum import Enum
from typing import List, Optional

from sqlmodel import SQLModel

from ..contribuyentes.modelos import EstadoPeriodo, TipoContribuyente
from ..parametros.modelos import VencimientoDeclaracion
from ..portal.modelos import ResumenRequerimientos


class OrdenCartera(str, Enum):
    ALERTAS = "alertas"
    NOMBRE = "nombre"
    VENCIMIENTO = "vencimiento"
    # Ordena por lo que falta recoger: primero a quien le faltan más soportes
    # y quien marcó «no entiendo». Es el orden útil cuando el panel se usa
    # como pantalla de entrada y la pregunta es «¿a quién le escribo hoy?».
    PENDIENTES = "pendientes"


class FilaCartera(SQLModel):
    contribuyente_id: int
    nombre: str
    rut: str
    tipo_contribuyente: TipoContribuyente
    periodo_fiscal_id: Optional[int] = None
    anio_gravable: Optional[int] = None
    estado_periodo: Optional[EstadoPeriodo] = None
    obligado: Optional[bool] = None
    alertas_no_declarado: Optional[int] = None
    vencimiento: Optional[VencimientoDeclaracion] = None
    # Etapa pendiente del proceso (gestion) y avance.
    etapa_actual: Optional[str] = None
    etapa_nombre: Optional[str] = None
    etapas_hechas: Optional[int] = None
    etapas_total: Optional[int] = None
    documentos_pendientes: Optional[int] = None
    avisos: List[str] = []

    # Estado de la recolección de soportes: lo que el panel necesita para
    # responder «a quién le falta qué» sin entrar a la ficha.
    exogena_cargada: bool = False
    fecha_corte_exogena: Optional[date] = None
    version_exogena: Optional[int] = None
    enlace_vigente: bool = False
    enlace_ultimo_acceso: Optional[date] = None
    politica_aceptada: bool = False
    requerimientos: ResumenRequerimientos = ResumenRequerimientos()


class PanelCartera(SQLModel):
    anio_gravable: Optional[int]
    total_contribuyentes: int
    total_obligados: int
    total_alertas: int
    total_vencidas: int = 0
    total_proximas: int = 0
    total_soportes_pendientes: int = 0
    total_no_entiendo: int = 0
    total_conceptos_sin_reconocer: int = 0
    total_sin_enlace: int = 0
    contribuyentes: List[FilaCartera]
