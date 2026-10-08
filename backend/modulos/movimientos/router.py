from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ContribuyenteNoEncontradoError,
    DocumentoSoporteDuplicadoError,
    DocumentoSoporteNoEncontradoError,
    InventarioNoAplicaError,
    MovimientoInvalidoError,
    PeriodoFiscalCerradoError,
    PeriodoFiscalNoEncontradoError,
    ProductoInactivoError,
    ProductoNoEncontradoError,
    ProveedorDuplicadoError,
    ProveedorNoEncontradoError,
    StockInsuficienteError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import (
    CostoVentasPeriodo,
    DocumentoSoporteCrear,
    DocumentoSoporteLeer,
    Kardex,
    KardexProductoPeriodo,
    MovimientoCrear,
    MovimientoLeer,
    ProveedorCrear,
    ProveedorLeer,
    TipoMovimiento,
)

router = APIRouter(prefix="/contribuyentes", tags=["movimientos"])

_NO_ENCONTRADO = (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    ProductoNoEncontradoError,
    ProveedorNoEncontradoError,
    DocumentoSoporteNoEncontradoError,
)
_CONFLICTO = (
    InventarioNoAplicaError,
    ProveedorDuplicadoError,
    DocumentoSoporteDuplicadoError,
    PeriodoFiscalCerradoError,
    ProductoInactivoError,
    StockInsuficienteError,
)
_ERRORES = _NO_ENCONTRADO + _CONFLICTO + (MovimientoInvalidoError,)


def _traducir(exc: Exception) -> HTTPException:
    if isinstance(exc, _NO_ENCONTRADO):
        codigo = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, MovimientoInvalidoError):
        codigo = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        codigo = status.HTTP_409_CONFLICT
    return HTTPException(status_code=codigo, detail=str(exc))


# -------------------------------------------------------------------- Proveedor


@router.post(
    "/{contribuyente_id}/proveedores",
    response_model=ProveedorLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_proveedor(
    contribuyente_id: int,
    datos: ProveedorCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-13: 409 si ya existe un proveedor con esa identificación."""
    try:
        return servicios.crear_proveedor(session, contador.id, contribuyente_id, datos)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get("/{contribuyente_id}/proveedores", response_model=List[ProveedorLeer])
def listar_proveedores(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_proveedores(session, contador.id, contribuyente_id)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


# ------------------------------------------------------------- DocumentoSoporte


@router.post(
    "/{contribuyente_id}/documentos-soporte",
    response_model=DocumentoSoporteLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_documento_soporte(
    contribuyente_id: int,
    datos: DocumentoSoporteCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-12: el documento que luego respalda uno o varios movimientos."""
    try:
        return servicios.crear_documento_soporte(
            session, contador.id, contribuyente_id, datos
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get(
    "/{contribuyente_id}/documentos-soporte", response_model=List[DocumentoSoporteLeer]
)
def listar_documentos_soporte(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_documentos_soporte(
            session, contador.id, contribuyente_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


# ------------------------------------------------------------------- Movimiento


@router.post(
    "/{contribuyente_id}/movimientos",
    response_model=MovimientoLeer,
    status_code=status.HTTP_201_CREATED,
)
def registrar_movimiento(
    contribuyente_id: int,
    datos: MovimientoCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-12. 409 por stock insuficiente, producto inactivo o periodo
    cerrado; 422 si la fecha no cae en el año del periodo o si una salida
    trae proveedor."""
    try:
        return servicios.registrar_movimiento(
            session, contador.id, contribuyente_id, datos
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get("/{contribuyente_id}/movimientos", response_model=List[MovimientoLeer])
def listar_movimientos(
    contribuyente_id: int,
    producto_id: Optional[int] = None,
    periodo_fiscal_id: Optional[int] = None,
    tipo: Optional[TipoMovimiento] = None,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_movimientos(
            session, contador.id, contribuyente_id, producto_id, periodo_fiscal_id, tipo
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


# ------------------------------------------------------- Kardex y costo de ventas


@router.get(
    "/{contribuyente_id}/productos/{producto_id}/kardex", response_model=Kardex
)
def kardex(
    contribuyente_id: int,
    producto_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-14: histórico de movimientos del producto con costo y saldo."""
    try:
        return servicios.obtener_kardex(
            session, contador.id, contribuyente_id, producto_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/kardex",
    response_model=List[KardexProductoPeriodo],
)
def kardex_del_periodo(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Kardex de todos los productos en el periodo, con saldo inicial y
    final (HU-16)."""
    try:
        return servicios.kardex_por_periodo(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/costo-ventas",
    response_model=CostoVentasPeriodo,
)
def costo_ventas(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-14: costo de ventas e inventario final del periodo, por producto."""
    try:
        return servicios.calcular_costo_ventas(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc
