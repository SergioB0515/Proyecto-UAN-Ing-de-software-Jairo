"""Endpoints del portal del lado del contador (con sesión).

Lo que un contribuyente puede hacer con su token está en `router_publico.py`.
Están separados a propósito: así se puede leer de un tirón todo lo que el
enlace permite, sin tener que revisar qué dependencia protege cada ruta.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    AnioGravableNoSoportadoError,
    ContribuyenteNoEncontradoError,
    DatoAdicionalNoEncontradoError,
    EnlaceCargaNoEncontradoError,
    PeriodoFiscalCerradoError,
    PeriodoFiscalNoEncontradoError,
    RequerimientoNoEncontradoError,
    ReporteExogenaNoEncontradoError,
    TopeAdicionalExcedidoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from ..contribuyentes.servicios import obtener_periodo_fiscal
from ..exogena.servicios import obtener_reporte_mas_reciente
from . import servicios
from .modelos import (
    DatoAdicionalCrear,
    DatoAdicionalLeer,
    EnlaceCargaCreado,
    EnlaceCargaCrear,
    EnlaceCargaLeer,
    ParametrosAdicionales,
    RequerimientoLeer,
    ResumenRequerimientos,
)

router = APIRouter(prefix="/contribuyentes", tags=["portal"])

_NO_ENCONTRADO = (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    EnlaceCargaNoEncontradoError,
    RequerimientoNoEncontradoError,
    DatoAdicionalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
)
_CONFLICTO = (PeriodoFiscalCerradoError, AnioGravableNoSoportadoError)
_ERRORES = _NO_ENCONTRADO + _CONFLICTO + (TopeAdicionalExcedidoError,)


def _traducir(exc: Exception) -> HTTPException:
    if isinstance(exc, _NO_ENCONTRADO):
        codigo = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, TopeAdicionalExcedidoError):
        codigo = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        codigo = status.HTTP_409_CONFLICT
    return HTTPException(status_code=codigo, detail=str(exc))


# ---------------------------------------------------------------------------
# Enlaces de carga
# ---------------------------------------------------------------------------


@router.post(
    "/{contribuyente_id}/enlaces-carga",
    response_model=EnlaceCargaCreado,
    status_code=status.HTTP_201_CREATED,
    name="generar_enlace_carga",
)
def generar_enlace_carga(
    contribuyente_id: int,
    datos: EnlaceCargaCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Genera el enlace. El token viaja UNA sola vez, en esta respuesta."""
    try:
        return servicios.crear_enlace(session, contador.id, contribuyente_id, datos)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get("/{contribuyente_id}/enlaces-carga", response_model=List[EnlaceCargaLeer])
def listar_enlaces_carga(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_enlaces(session, contador.id, contribuyente_id)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.post(
    "/{contribuyente_id}/enlaces-carga/{enlace_id}/revocar",
    response_model=EnlaceCargaLeer,
    name="revocar_enlace_carga",
)
def revocar_enlace_carga(
    contribuyente_id: int,
    enlace_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.revocar_enlace(
            session, contador.id, contribuyente_id, enlace_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


# ---------------------------------------------------------------------------
# Requerimientos
# ---------------------------------------------------------------------------


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/requerimientos",
    response_model=List[RequerimientoLeer],
)
def listar_requerimientos(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        obtener_periodo_fiscal(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
        return servicios.listar_requerimientos(
            session, contribuyente_id, periodo_fiscal_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/requerimientos/resumen",
    response_model=ResumenRequerimientos,
)
def resumen_requerimientos(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        obtener_periodo_fiscal(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
        return servicios.resumen_del_periodo(
            session, contribuyente_id, periodo_fiscal_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.post(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/requerimientos/sincronizar",
    response_model=List[RequerimientoLeer],
    name="sincronizar_requerimientos",
)
def sincronizar_requerimientos(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Vuelve a traducir la exógena vigente a requerimientos.

    Existe para el caso en que el contador cargó el archivo él mismo antes de
    que existiera el enlace. Es idempotente: no borra el estado ni los
    archivos que el contribuyente ya hubiera puesto.
    """
    try:
        obtener_periodo_fiscal(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
        reporte = obtener_reporte_mas_reciente(session, periodo_fiscal_id)
        servicios.sincronizar_requerimientos(session, reporte)
        return servicios.listar_requerimientos(
            session, contribuyente_id, periodo_fiscal_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.patch(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}"
    "/requerimientos/{requerimiento_id}/revision",
    response_model=RequerimientoLeer,
    name="marcar_requerimiento_revisado",
)
def marcar_requerimiento_revisado(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    requerimiento_id: int,
    revisado: bool = True,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Da por resuelto un concepto que la aplicación no supo clasificar."""
    try:
        return servicios.marcar_revisado(
            session,
            contador.id,
            contribuyente_id,
            periodo_fiscal_id,
            requerimiento_id,
            revisado,
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


# ---------------------------------------------------------------------------
# Adicionales
# ---------------------------------------------------------------------------


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/adicionales/parametros",
    response_model=ParametrosAdicionales,
)
def parametros_adicionales(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        periodo = obtener_periodo_fiscal(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
        return servicios.parametros_adicionales(periodo.anio_gravable)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/adicionales",
    response_model=List[DatoAdicionalLeer],
)
def listar_adicionales(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        obtener_periodo_fiscal(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
        return servicios.listar_adicionales(
            session, contribuyente_id, periodo_fiscal_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.post(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/adicionales",
    response_model=DatoAdicionalLeer,
    status_code=status.HTTP_201_CREATED,
    name="crear_dato_adicional",
)
def crear_dato_adicional(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: DatoAdicionalCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        obtener_periodo_fiscal(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
        return servicios.agregar_adicional(
            session,
            contribuyente_id,
            periodo_fiscal_id,
            datos,
            capturado_en_portal=False,
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.delete(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/adicionales/{adicional_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="eliminar_dato_adicional",
)
def eliminar_dato_adicional(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    adicional_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        obtener_periodo_fiscal(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
        servicios.eliminar_adicional(
            session, contribuyente_id, periodo_fiscal_id, adicional_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc
