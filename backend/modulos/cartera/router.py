from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from ..reportes.modelos import FormatoReporte
from ..reportes.servicios import _MEDIA_TYPES
from .modelos import OrdenCartera, PanelCartera

router = APIRouter(prefix="/cartera", tags=["cartera"])


@router.get("", response_model=PanelCartera)
def panel(
    anio_gravable: Optional[int] = Query(default=None, ge=2000, le=2100),
    orden: OrdenCartera = OrdenCartera.ALERTAS,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    return servicios.panel_cartera(session, contador.id, anio_gravable, orden)


@router.get("/exportar", response_class=Response)
def exportar_cartera(
    anio_gravable: Optional[int] = Query(default=None, ge=2000, le=2100),
    orden: OrdenCartera = OrdenCartera.ALERTAS,
    formato: FormatoReporte = FormatoReporte.XLSX,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    panel = servicios.panel_cartera(session, contador.id, anio_gravable, orden)
    contenido, nombre = servicios.exportar_panel(panel, formato.value, contador.nombre)
    return Response(
        content=contenido,
        media_type=_MEDIA_TYPES[formato],
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
