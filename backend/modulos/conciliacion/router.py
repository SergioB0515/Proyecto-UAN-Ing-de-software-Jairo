from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ContribuyenteNoEncontradoError,
    DecisionRenglonInvalidaError,
    PeriodoFiscalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import (
    BorradorRenglones,
    CruceDian,
    DecisionRenglonFijar,
    DecisionRenglonLeer,
    ResultadoConciliacion,
)

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
    """Cruce con la DIAN: cuadre de topes y comparación de patrimonio, ingresos,
    retenciones y GO.
    """
    try:
        return servicios.cruzar_con_la_dian(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _NO_ENCONTRADO as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

# ---------------------------------------------------------------------------
# Valor final de cada renglón
#
# Estas tres rutas son del contador y de nadie más: el portal del
# contribuyente no tiene una equivalente. Él informa y aporta soportes; quien
# decide qué se declara es quien firma la declaración.
# ---------------------------------------------------------------------------


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/conciliacion/decisiones",
    response_model=List[DecisionRenglonLeer],
)
def listar_decisiones(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_decisiones(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _NO_ENCONTRADO as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.put(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/conciliacion/decisiones",
    response_model=DecisionRenglonLeer,
    name="fijar_decision_renglon",
)
def fijar_decision_renglon(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: DecisionRenglonFijar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Fija el valor final de un renglón y deja registrada la fuente elegida."""
    try:
        return servicios.fijar_decision(
            session, contador.id, contribuyente_id, periodo_fiscal_id, datos
        )
    except _NO_ENCONTRADO as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except DecisionRenglonInvalidaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.delete(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}"
    "/conciliacion/decisiones/{clave_item}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="borrar_decision_renglon",
)
def borrar_decision_renglon(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    clave_item: str,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.borrar_decision(
            session, contador.id, contribuyente_id, periodo_fiscal_id, clave_item
        )
    except _NO_ENCONTRADO as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except DecisionRenglonInvalidaError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
