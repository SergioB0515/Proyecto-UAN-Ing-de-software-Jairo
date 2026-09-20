from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
    UmbralNoConfiguradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import (
    ResultadoObligacion,
    UmbralDeclaracionCrear,
    UmbralDeclaracionLeer,
)

router = APIRouter(prefix="/parametros", tags=["parametros"])


@router.post(
    "/umbrales", response_model=UmbralDeclaracionLeer, status_code=status.HTTP_201_CREATED
)
def registrar_umbral(
    datos: UmbralDeclaracionCrear,
    # Cualquier contador autenticado puede registrar umbrales — es un dato
    # compartido, no exclusivo de su cartera (documentacion/04-arquitectura.md).
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    return servicios.registrar_umbral(session, datos)


@router.get("/umbrales", response_model=List[UmbralDeclaracionLeer])
def listar_umbrales(
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    return servicios.listar_umbrales(session)


@router.get(
    "/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/obligacion",
    response_model=ResultadoObligacion,
)
def verificar_obligacion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-07."""
    try:
        return servicios.verificar_obligacion_declarar(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except (
        ContribuyenteNoEncontradoError,
        PeriodoFiscalNoEncontradoError,
        ReporteExogenaNoEncontradoError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except UmbralNoConfiguradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
