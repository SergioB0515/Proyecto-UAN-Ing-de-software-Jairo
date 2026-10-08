from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import EventoAuditoriaLeer, IntentoAccesoLeer

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


@router.get("", response_model=List[EventoAuditoriaLeer])
def listar_eventos(
    contribuyente_id: Optional[int] = None,
    limite: int = Query(default=100, ge=1, le=500),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Acciones del contador autenticado, la más reciente primero."""
    return [
        EventoAuditoriaLeer(**evento.model_dump(), nombre_contribuyente=nombre)
        for evento, nombre in servicios.listar_eventos(
            session, contador.id, contribuyente_id, limite
        )
    ]


@router.get("/accesos", response_model=List[IntentoAccesoLeer])
def listar_accesos(
    limite: int = Query(default=50, ge=1, le=200),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Intentos de inicio de sesión con el email del contador: le permite
    ver si alguien intentó entrar a su cuenta."""
    return servicios.listar_accesos(session, contador.email, limite)
