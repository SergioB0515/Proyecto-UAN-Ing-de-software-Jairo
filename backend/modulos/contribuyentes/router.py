from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ActivoDeCierreError,
    ActivoNoEncontradoError,
    ContribuyenteConDatosError,
    ContribuyenteNoEncontradoError,
    FuenteIngresoNoEncontradaError,
    PeriodoFiscalCerradoError,
    PeriodoFiscalDuplicadoError,
    PeriodoFiscalNoEncontradoError,
    SinPeriodoAnteriorError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import (
    ActivoActualizar,
    ActivoCrear,
    ActivoLeer,
    ContribuyenteActualizar,
    ContribuyenteConPatrimonio,
    ContribuyenteCrear,
    ContribuyenteLeer,
    FuenteIngresoActualizar,
    FuenteIngresoCrear,
    FuenteIngresoLeer,
    PeriodoFiscalActualizar,
    PeriodoFiscalCrear,
    PeriodoFiscalLeer,
)

router = APIRouter(prefix="/contribuyentes", tags=["contribuyentes"])


_NO_ENCONTRADO = (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    ActivoNoEncontradoError,
    FuenteIngresoNoEncontradaError,
)
_CONFLICTO = (
    PeriodoFiscalCerradoError,
    ActivoDeCierreError,
    ContribuyenteConDatosError,
    SinPeriodoAnteriorError,
)


def _traducir(exc: Exception) -> HTTPException:
    return _no_encontrado(exc) if isinstance(exc, _NO_ENCONTRADO) else _conflicto(exc)


def _no_encontrado(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _conflicto(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "", response_model=ContribuyenteLeer, status_code=status.HTTP_201_CREATED
)
def crear(
    datos: ContribuyenteCrear,
    request: Request,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    creado = servicios.crear_contribuyente(session, contador.id, datos)
    request.state.auditoria_contribuyente_id = creado.id
    return creado


@router.get("", response_model=List[ContribuyenteLeer])
def listar(
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    return servicios.listar_contribuyentes(session, contador.id)


@router.get("/{contribuyente_id}", response_model=ContribuyenteLeer)
def obtener(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.obtener_contribuyente(session, contador.id, contribuyente_id)
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc


@router.get("/{contribuyente_id}/patrimonio", response_model=ContribuyenteConPatrimonio)
def ver_patrimonio(
    contribuyente_id: int,
    periodo_fiscal_id: Optional[int] = Query(
        default=None, description="Por defecto, el periodo más reciente."
    ),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        contribuyente = servicios.obtener_contribuyente(
            session, contador.id, contribuyente_id
        )
        if periodo_fiscal_id is not None:
            periodo = servicios.obtener_periodo_fiscal(
                session, contador.id, contribuyente_id, periodo_fiscal_id
            )
        else:
            periodo = servicios.periodo_mas_reciente(
                session, contador.id, contribuyente_id
            )
        patrimonio = (
            servicios.calcular_patrimonio_liquido(
                session, contador.id, contribuyente_id, periodo.id
            )
            if periodo is not None
            else 0.0
        )
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc

    return ContribuyenteConPatrimonio(
        **contribuyente.model_dump(),
        patrimonio_liquido=patrimonio,
        periodo_fiscal_id=periodo.id if periodo is not None else None,
        anio_gravable=periodo.anio_gravable if periodo is not None else None,
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
    try:
        return servicios.agregar_activo(
            session, contador.id, contribuyente_id, datos
        )
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc
    except PeriodoFiscalCerradoError as exc:
        raise _conflicto(exc) from exc


@router.get("/{contribuyente_id}/activos", response_model=List[ActivoLeer])
def listar_activos(
    contribuyente_id: int,
    periodo_fiscal_id: Optional[int] = None,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_activos(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _NO_ENCONTRADO as exc:
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
    try:
        return servicios.crear_periodo_fiscal(
            session, contador.id, contribuyente_id, datos
        )
    except ContribuyenteNoEncontradoError as exc:
        raise _no_encontrado(exc) from exc
    except PeriodoFiscalDuplicadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


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
    try:
        return servicios.agregar_fuente_ingreso(
            session, contador.id, contribuyente_id, datos
        )
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc
    except PeriodoFiscalCerradoError as exc:
        raise _conflicto(exc) from exc


@router.get(
    "/{contribuyente_id}/fuentes-ingreso", response_model=List[FuenteIngresoLeer]
)
def listar_fuentes_ingreso(
    contribuyente_id: int,
    periodo_fiscal_id: Optional[int] = None,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_fuentes_ingreso(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc


@router.patch("/{contribuyente_id}", response_model=ContribuyenteLeer)
def actualizar(
    contribuyente_id: int,
    cambios: ContribuyenteActualizar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.actualizar_contribuyente(session, contador.id, contribuyente_id, cambios)
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.delete("/{contribuyente_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.eliminar_contribuyente(session, contador.id, contribuyente_id)
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.patch("/{contribuyente_id}/activos/{activo_id}", response_model=ActivoLeer)
def actualizar_activo(
    contribuyente_id: int,
    activo_id: int,
    cambios: ActivoActualizar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.actualizar_activo(
            session, contador.id, contribuyente_id, activo_id, cambios
        )
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.delete(
    "/{contribuyente_id}/activos/{activo_id}", status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_activo(
    contribuyente_id: int,
    activo_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.eliminar_activo(session, contador.id, contribuyente_id, activo_id)
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.patch(
    "/{contribuyente_id}/fuentes-ingreso/{fuente_id}", response_model=FuenteIngresoLeer
)
def actualizar_fuente_ingreso(
    contribuyente_id: int,
    fuente_id: int,
    cambios: FuenteIngresoActualizar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.actualizar_fuente_ingreso(
            session, contador.id, contribuyente_id, fuente_id, cambios
        )
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.delete(
    "/{contribuyente_id}/fuentes-ingreso/{fuente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_fuente_ingreso(
    contribuyente_id: int,
    fuente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.eliminar_fuente_ingreso(session, contador.id, contribuyente_id, fuente_id)
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.post(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/copiar-activos",
    response_model=List[ActivoLeer],
    status_code=status.HTTP_201_CREATED,
)
def copiar_activos(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.copiar_activos_del_anio_anterior(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.patch(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}",
    response_model=PeriodoFiscalLeer,
)
def actualizar_periodo_fiscal(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    cambios: PeriodoFiscalActualizar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.actualizar_periodo_fiscal(
            session, contador.id, contribuyente_id, periodo_fiscal_id, cambios
        )
    except _NO_ENCONTRADO as exc:
        raise _traducir(exc) from exc
