"""Bloqueo por intentos fallidos de inicio de sesión y registro de acciones.

El bloqueo es por email: con LIMITE_FALLOS intentos fallidos dentro de
VENTANA (y después del último acceso exitoso), la cuenta queda bloqueada
hasta que el más antiguo de esos fallos salga de la ventana. Los intentos
hechos durante el bloqueo se registran como BLOQUEADO y no cuentan como
fallos: así un atacante insistiendo no extiende indefinidamente el bloqueo
del usuario legítimo.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlmodel import Session, select

from core.excepciones import CuentaBloqueadaError

from .modelos import EventoAuditoria, IntentoAcceso, ResultadoAcceso

LIMITE_FALLOS = 5
VENTANA = timedelta(minutes=15)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _como_utc(fecha: datetime) -> datetime:
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def bloqueado_hasta(session: Session, email: str, ahora: Optional[datetime] = None) -> Optional[datetime]:
    """Hasta cuándo está bloqueado el email, o None si no lo está."""
    ahora = ahora or _ahora()
    desde = ahora - VENTANA
    ultimo_exito = session.exec(
        select(IntentoAcceso.fecha)
        .where(IntentoAcceso.email == email, IntentoAcceso.resultado == ResultadoAcceso.EXITOSO)
        .order_by(IntentoAcceso.fecha.desc())
    ).first()
    if ultimo_exito is not None:
        desde = max(desde, _como_utc(ultimo_exito))

    fallos = session.exec(
        select(IntentoAcceso.fecha)
        .where(
            IntentoAcceso.email == email,
            IntentoAcceso.resultado == ResultadoAcceso.FALLIDO,
            IntentoAcceso.fecha > desde,
        )
        .order_by(IntentoAcceso.fecha.desc())
        .limit(LIMITE_FALLOS)
    ).all()
    if len(fallos) < LIMITE_FALLOS:
        return None
    return _como_utc(fallos[-1]) + VENTANA


def verificar_no_bloqueado(session: Session, email: str, ip: Optional[str]) -> None:
    hasta = bloqueado_hasta(session, email)
    if hasta is None:
        return
    registrar_intento(session, email, ResultadoAcceso.BLOQUEADO, ip)
    minutos = max(1, int((hasta - _ahora()).total_seconds() // 60) + 1)
    raise CuentaBloqueadaError(
        f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} minuto(s).",
        segundos=int((hasta - _ahora()).total_seconds()) + 1,
    )


def registrar_intento(
    session: Session, email: str, resultado: ResultadoAcceso, ip: Optional[str]
) -> None:
    session.add(IntentoAcceso(email=email, resultado=resultado, ip=ip))
    session.commit()


def listar_accesos(session: Session, email: str, limite: int = 50) -> List[IntentoAcceso]:
    return list(
        session.exec(
            select(IntentoAcceso)
            .where(IntentoAcceso.email == email)
            .order_by(IntentoAcceso.fecha.desc(), IntentoAcceso.id.desc())
            .limit(limite)
        ).all()
    )


def registrar_evento(session: Session, evento: EventoAuditoria) -> None:
    session.add(evento)
    session.commit()


def listar_eventos(
    session: Session,
    contador_id: int,
    contribuyente_id: Optional[int] = None,
    limite: int = 100,
) -> list:
    """Eventos del contador, el más reciente primero, con el nombre del
    contribuyente si todavía existe."""
    from ..contribuyentes.modelos import Contribuyente

    consulta = (
        select(EventoAuditoria, Contribuyente.nombre)
        .join(
            Contribuyente,
            Contribuyente.id == EventoAuditoria.contribuyente_id,
            isouter=True,
        )
        .where(EventoAuditoria.contador_id == contador_id)
    )
    if contribuyente_id is not None:
        consulta = consulta.where(EventoAuditoria.contribuyente_id == contribuyente_id)
    return list(
        session.exec(
            consulta.order_by(EventoAuditoria.fecha.desc(), EventoAuditoria.id.desc()).limit(limite)
        ).all()
    )
