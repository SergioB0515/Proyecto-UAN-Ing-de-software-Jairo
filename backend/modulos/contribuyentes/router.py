from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import ContribuyenteNoEncontradoError
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import (
    ActivoCrear,
    ActivoLeer,
    ContribuyenteConPatrimonio,
    ContribuyenteCrear,
    ContribuyenteLeer,
    FuenteIngresoCrear,
    FuenteIngresoLeer,
    PeriodoFiscalCrear,
    PeriodoFiscalLeer,
)

router = APIRouter(prefix="/contribuyentes", tags=["contribuyentes"])


def _no_encontrado(exc: ContribuyenteNoEncontradoError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "", response_model=ContribuyenteLeer, status_code=status.HTTP_201_CREATED
)
def crear(
    datos: ContribuyenteCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-02."""
    return servicios.crear_contribuyente(session, contador.id, datos)


@router.get("", response_model=List[ContribuyenteLeer])
def listar(
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-02: solo los contribuyentes del contador autenticado."""
    return servicios.listar_contribuyentes(session, contador.id)


@router.get("/{contribuyente_id}/patrimonio", response_model=ContribuyenteConPatrimonio)
def ver_patrimonio(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-04: datos del contribuyente + su patrimonio líquido calculado."""
    try:
        contribuyente = servicios.obtener_contribuyente(
            session, contador.id, contribuyente_id
        )
        patrimonio = servicios.calcular_patrimonio_liquido(
            session, contador.id, contribuyente_id
        )
    except ContribuyenteNoEncontradoError as exc:
        raise _no_encontrado(exc) from exc

    return ContribuyenteConPatrimonio(
        **contribuyente.model_dump(), patrimonio_liquido=patrimonio
    )


@router.post(
    "/{contribuyente_id}/activos",
    response_model=ActivoLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_activo(
    contribuyente_id: int,
    datos: ActivoCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-04."""
    try:
        return servicios.agregar_activo(
            session, contador.id, contribuyente_id, datos
        )
    except ContribuyenteNoEncontradoError as exc:
        raise _no_encontrado(exc) from exc


@router.get("/{contribuyente_id}/activos", response_model=List[ActivoLeer])
def listar_activos(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_activos(session, contador.id, contribuyente_id)
    except ContribuyenteNoEncontradoError as exc:
        raise _no_encontrado(exc) from exc


@router.post(
    "/{contribuyente_id}/periodos-fiscales",
    response_model=PeriodoFiscalLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_periodo_fiscal(
    contribuyente_id: int,
    datos: PeriodoFiscalCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Nuevo en el Incremento 2."""
    try:
        return servicios.crear_periodo_fiscal(
            session, contador.id, contribuyente_id, datos
        )
    except ContribuyenteNoEncontradoError as exc:
        raise _no_encontrado(exc) from exc


@router.get(
    "/{contribuyente_id}/periodos-fiscales", response_model=List[PeriodoFiscalLeer]
)
def listar_periodos_fiscales(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_periodos_fiscales(
            session, contador.id, contribuyente_id
        )
    except ContribuyenteNoEncontradoError as exc:
        raise _no_encontrado(exc) from exc


@router.post(
    "/{contribuyente_id}/fuentes-ingreso",
    response_model=FuenteIngresoLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_fuente_ingreso(
    contribuyente_id: int,
    datos: FuenteIngresoCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-03."""
    try:
        return servicios.agregar_fuente_ingreso(
            session, contador.id, contribuyente_id, datos
        )
    except ContribuyenteNoEncontradoError as exc:
        raise _no_encontrado(exc) from exc


@router.get(
    "/{contribuyente_id}/fuentes-ingreso", response_model=List[FuenteIngresoLeer]
)
def listar_fuentes_ingreso(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_fuentes_ingreso(
            session, contador.id, contribuyente_id
        )
    except ContribuyenteNoEncontradoError as exc:
        raise _no_encontrado(exc) from exc
