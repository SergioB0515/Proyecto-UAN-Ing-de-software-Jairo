from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import BorradorRenglones, CruceDian, ResultadoConciliacion

router = APIRouter(prefix="/contribuyentes", tags=["conciliacion"])

_NO_ENCONTRADO = (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
)


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/conciliacion",
    response_model=ResultadoConciliacion,
)
def conciliar(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.conciliar_contribuyente(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _NO_ENCONTRADO as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/borrador-renglones",
    response_model=BorradorRenglones,
)
def borrador_renglones(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.generar_borrador_renglones(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _NO_ENCONTRADO as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/cruce-dian",
    response_model=CruceDian,
)
def cruce_dian(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Compara el borrador de liquidación con lo que la DIAN ya sabe.

    Reconstruye los cinco topes desde el detalle de la exógena y contrasta el
    patrimonio, los ingresos, las retenciones y las ganancias ocasionales que
    se van a declarar con lo que reportaron los terceros.
    """
    try:
        return servicios.cruzar_con_la_dian(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _NO_ENCONTRADO as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
