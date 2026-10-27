from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    CalendarioInvalidoError,
    CalendarioOficialNoDisponibleError,
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
    UmbralNoConfiguradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import (
    PlazoDeclaracionDatos,
    PlazoDeclaracionLeer,
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


_ANIO = Path(ge=2000, le=2100)


@router.get("/plazos/{anio_gravable}", response_model=List[PlazoDeclaracionLeer])
def listar_plazos(
    anio_gravable: int = _ANIO,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    return servicios.listar_plazos(session, anio_gravable)


@router.put("/plazos/{anio_gravable}", response_model=List[PlazoDeclaracionLeer])
def reemplazar_plazos(
    plazos: List[PlazoDeclaracionDatos],
    anio_gravable: int = _ANIO,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.reemplazar_plazos(session, anio_gravable, plazos)
    except CalendarioInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post(
    "/plazos/{anio_gravable}/calendario-oficial", response_model=List[PlazoDeclaracionLeer]
)
def cargar_calendario_oficial(
    anio_gravable: int = _ANIO,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.cargar_calendario_oficial(session, anio_gravable)
    except CalendarioOficialNoDisponibleError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
