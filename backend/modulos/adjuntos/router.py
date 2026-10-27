from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ActivoDeCierreError,
    AdjuntoDuplicadoError,
    AdjuntoNoEncontradoError,
    ArchivoDemasiadoGrandeError,
    ArchivoNoPermitidoError,
    ContribuyenteNoEncontradoError,
    EntidadAdjuntoNoEncontradaError,
    PeriodoFiscalCerradoError,
    PeriodoFiscalNoEncontradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import (
    AdjuntoActualizar,
    AdjuntoLeer,
    CategoriaAdjunto,
    ConteoAdjuntos,
    TipoEntidadAdjunto,
)

router = APIRouter(prefix="/contribuyentes", tags=["adjuntos"])

_NO_ENCONTRADO = (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    AdjuntoNoEncontradoError,
    EntidadAdjuntoNoEncontradaError,
)
_CONFLICTO = (AdjuntoDuplicadoError, PeriodoFiscalCerradoError, ActivoDeCierreError)
_ERRORES = _NO_ENCONTRADO + _CONFLICTO + (ArchivoDemasiadoGrandeError, ArchivoNoPermitidoError)


def _traducir(exc: Exception) -> HTTPException:
    if isinstance(exc, _NO_ENCONTRADO):
        codigo = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ArchivoDemasiadoGrandeError):
        codigo = status.HTTP_413_CONTENT_TOO_LARGE
    elif isinstance(exc, ArchivoNoPermitidoError):
        codigo = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    else:
        codigo = status.HTTP_409_CONFLICT
    return HTTPException(status_code=codigo, detail=str(exc))


@router.post(
    "/{contribuyente_id}/adjuntos",
    response_model=AdjuntoLeer,
    status_code=status.HTTP_201_CREATED,
)
def subir_adjunto(
    contribuyente_id: int,
    entidad_tipo: TipoEntidadAdjunto = Form(...),
    entidad_id: int = Form(...),
    categoria: CategoriaAdjunto = Form(CategoriaAdjunto.OTRO),
    descripcion: Optional[str] = Form(None, max_length=300),
    archivo: UploadFile = File(...),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.adjuntar_archivo(
            session,
            contador.id,
            contribuyente_id,
            entidad_tipo,
            entidad_id,
            archivo.file,
            archivo.filename,
            categoria,
            descripcion,
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get("/{contribuyente_id}/adjuntos", response_model=List[AdjuntoLeer])
def listar_adjuntos(
    contribuyente_id: int,
    entidad_tipo: Optional[TipoEntidadAdjunto] = None,
    entidad_id: Optional[int] = None,
    periodo_fiscal_id: Optional[int] = None,
    categoria: Optional[CategoriaAdjunto] = None,
    q: Optional[str] = Query(default=None, max_length=100),
    incluir_generales: bool = False,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_adjuntos(
            session,
            contador.id,
            contribuyente_id,
            entidad_tipo,
            entidad_id,
            periodo_fiscal_id,
            categoria,
            q,
            incluir_generales,
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get("/{contribuyente_id}/adjuntos/resumen", response_model=List[ConteoAdjuntos])
def resumen_adjuntos(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.contar_adjuntos(session, contador.id, contribuyente_id)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get(
    "/{contribuyente_id}/adjuntos/{adjunto_id}/archivo",
    response_class=FileResponse,
)
def ver_adjunto(
    contribuyente_id: int,
    adjunto_id: int,
    descargar: bool = False,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        adjunto, ruta = servicios.obtener_archivo(
            session, contador.id, contribuyente_id, adjunto_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc
    en_linea = adjunto.tipo_mime in servicios.TIPOS_PREVISUALIZABLES and not descargar
    return FileResponse(
        ruta,
        media_type=adjunto.tipo_mime,
        filename=adjunto.nombre_original,
        content_disposition_type="inline" if en_linea else "attachment",
    )


@router.patch("/{contribuyente_id}/adjuntos/{adjunto_id}", response_model=AdjuntoLeer)
def actualizar_adjunto(
    contribuyente_id: int,
    adjunto_id: int,
    cambios: AdjuntoActualizar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.actualizar_adjunto(
            session, contador.id, contribuyente_id, adjunto_id, cambios
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.delete(
    "/{contribuyente_id}/adjuntos/{adjunto_id}", status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_adjunto(
    contribuyente_id: int,
    adjunto_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.eliminar_adjunto(session, contador.id, contribuyente_id, adjunto_id)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


def _leer_por_bloques(archivo, tamano_bloque: int = 1024 * 256):
    try:
        while True:
            bloque = archivo.read(tamano_bloque)
            if not bloque:
                break
            yield bloque
    finally:
        archivo.close()


@router.get(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/soportes/zip",
    response_class=StreamingResponse,
)
def descargar_soportes(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        archivo, tamano, nombre = servicios.comprimir_soportes(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc
    return StreamingResponse(
        _leer_por_bloques(archivo),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            "Content-Length": str(tamano),
        },
    )
