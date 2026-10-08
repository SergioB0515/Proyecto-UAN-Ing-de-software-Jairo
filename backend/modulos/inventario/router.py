from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    CategoriaConProductosActivosError,
    CategoriaNoEncontradaError,
    ContribuyenteNoEncontradoError,
    InventarioNoAplicaError,
    ProductoNoEncontradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import (
    CategoriaCrear,
    CategoriaLeer,
    ProductoActualizar,
    ProductoCrear,
    ProductoLeer,
)

router = APIRouter(prefix="/contribuyentes", tags=["inventario"])

_NO_ENCONTRADO = (
    ContribuyenteNoEncontradoError,
    CategoriaNoEncontradaError,
    ProductoNoEncontradoError,
)
_CONFLICTO = (InventarioNoAplicaError, CategoriaConProductosActivosError)


def _traducir(exc: Exception) -> HTTPException:
    if isinstance(exc, _NO_ENCONTRADO):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


# -------------------------------------------------------------------- Categoria


@router.post(
    "/{contribuyente_id}/categorias",
    response_model=CategoriaLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_categoria(
    contribuyente_id: int,
    datos: CategoriaCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-11."""
    try:
        return servicios.crear_categoria(session, contador.id, contribuyente_id, datos)
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.get("/{contribuyente_id}/categorias", response_model=List[CategoriaLeer])
def listar_categorias(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_categorias(session, contador.id, contribuyente_id)
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.delete(
    "/{contribuyente_id}/categorias/{categoria_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_categoria(
    contribuyente_id: int,
    categoria_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-11: 409 si la categoría tiene productos activos."""
    try:
        servicios.eliminar_categoria(
            session, contador.id, contribuyente_id, categoria_id
        )
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


# --------------------------------------------------------------------- Producto


@router.post(
    "/{contribuyente_id}/productos",
    response_model=ProductoLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_producto(
    contribuyente_id: int,
    datos: ProductoCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-11."""
    try:
        return servicios.crear_producto(session, contador.id, contribuyente_id, datos)
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.get("/{contribuyente_id}/productos", response_model=List[ProductoLeer])
def listar_productos(
    contribuyente_id: int,
    solo_activos: bool = False,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_productos(
            session, contador.id, contribuyente_id, solo_activos
        )
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.get(
    "/{contribuyente_id}/productos/{producto_id}", response_model=ProductoLeer
)
def obtener_producto(
    contribuyente_id: int,
    producto_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.obtener_producto(
            session, contador.id, contribuyente_id, producto_id
        )
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc


@router.patch(
    "/{contribuyente_id}/productos/{producto_id}", response_model=ProductoLeer
)
def actualizar_producto(
    contribuyente_id: int,
    producto_id: int,
    datos: ProductoActualizar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Incluye desactivar el producto (`activo: false`)."""
    try:
        return servicios.actualizar_producto(
            session, contador.id, contribuyente_id, producto_id, datos
        )
    except _NO_ENCONTRADO + _CONFLICTO as exc:
        raise _traducir(exc) from exc
