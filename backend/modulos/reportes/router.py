from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ContribuyenteNoEncontradoError,
    EstadoPeriodoInvalidoError,
    InventarioNoAplicaError,
    PeriodoFiscalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador
from modulos.contribuyentes.modelos import PeriodoFiscalLeer

from . import servicios
from .modelos import CierrePeriodoLeer, FormatoReporte, ResumenContribuyente, TipoReporte

router = APIRouter(prefix="/contribuyentes", tags=["reportes"])

_NO_ENCONTRADO = (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
)
_CONFLICTO = (EstadoPeriodoInvalidoError, InventarioNoAplicaError)
_ERRORES = _NO_ENCONTRADO + _CONFLICTO

_RUTA_PERIODO = "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}"


def _traducir(exc: Exception) -> HTTPException:
    codigo = (
        status.HTTP_404_NOT_FOUND
        if isinstance(exc, _NO_ENCONTRADO)
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=codigo, detail=str(exc))


@router.post(f"{_RUTA_PERIODO}/cerrar", response_model=CierrePeriodoLeer)
def cerrar_periodo(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-15: lleva el inventario final al patrimonio y marca el periodo
    CERRADO. 409 si ya está cerrado o hay años anteriores abiertos."""
    try:
        return servicios.cerrar_periodo(session, contador.id, contribuyente_id, periodo_fiscal_id)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.post(f"{_RUTA_PERIODO}/reabrir", response_model=PeriodoFiscalLeer)
def reabrir_periodo(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Deshace el cierre (para corregir). 409 si no está cerrado o hay años
    posteriores cerrados."""
    try:
        return servicios.reabrir_periodo(session, contador.id, contribuyente_id, periodo_fiscal_id)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get(f"{_RUTA_PERIODO}/resumen", response_model=ResumenContribuyente)
def resumen(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-17: patrimonio, ingresos, inventario (si aplica), obligación de
    declarar y conciliación del periodo en una sola respuesta."""
    try:
        return servicios.construir_resumen(session, contador.id, contribuyente_id, periodo_fiscal_id)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get(
    f"{_RUTA_PERIODO}/reportes/{{tipo}}",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "application/pdf": {},
            },
            "description": "El archivo del reporte.",
        }
    },
)
def descargar_reporte(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    tipo: TipoReporte,
    formato: FormatoReporte = FormatoReporte.XLSX,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-16: kardex, saldo de inventario, conciliación, borrador de
    renglones o resumen, en Excel (`formato=xlsx`) o PDF (`formato=pdf`).
    409 si se pide un reporte de inventario para un ASALARIADO; 404 si el
    reporte necesita exógena y aún no se importó."""
    try:
        contenido, media_type, nombre = servicios.generar_reporte(
            session, contador.id, contribuyente_id, periodo_fiscal_id, tipo, formato
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc
    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
