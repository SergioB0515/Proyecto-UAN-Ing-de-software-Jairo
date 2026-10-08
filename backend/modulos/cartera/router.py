from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import OrdenCartera, PanelCartera

router = APIRouter(prefix="/cartera", tags=["cartera"])


@router.get("", response_model=PanelCartera)
def panel(
    anio_gravable: Optional[int] = Query(default=None, ge=2000, le=2100),
    orden: OrdenCartera = OrdenCartera.ALERTAS,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-18. Sin `anio_gravable` evalúa el periodo más reciente de cada
    contribuyente."""
    return servicios.panel_cartera(session, contador.id, anio_gravable, orden)
