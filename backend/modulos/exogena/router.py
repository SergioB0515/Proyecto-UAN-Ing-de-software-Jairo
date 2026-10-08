from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ArchivoExogenaInvalidoError,
    ContribuyenteNoEncontradoError,
    PeriodoFiscalCerradoError,
    PeriodoFiscalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import (
    RegistroExogenaLeer,
    ReporteExogenaImportado,
    ReporteExogenaLeer,
    TopeExogenaLeer,
)

router = APIRouter(prefix="/contribuyentes", tags=["exogena"])

_NO_ENCONTRADO = (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
    ReporteExogenaNoEncontradoError,
)


def _no_encontrado(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/exogena",
    response_model=ReporteExogenaImportado,
    status_code=status.HTTP_201_CREATED,
)
def importar_exogena(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    archivo: UploadFile = File(...),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-05. El archivo se lee de forma síncrona (`archivo.file.read()`,
    no `await archivo.read()`) para mantener la ruta síncrona, coherente
    con la decisión de arquitectura del proyecto (documentacion/04-arquitectura.md).

    La respuesta incluye `errores`: las filas que no se pudieron
    interpretar, con su número de fila y el motivo."""
    contenido = archivo.file.read()
    try:
        return servicios.importar_reporte_exogena(
            session,
            contador.id,
            contribuyente_id,
            periodo_fiscal_id,
            contenido,
            archivo.filename or "archivo.xlsx",
        )
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc
    except PeriodoFiscalCerradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ArchivoExogenaInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/{contribuyente_id}/reportes-exogena", response_model=List[ReporteExogenaLeer]
)
def listar_reportes(
    contribuyente_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Reportes importados del contribuyente, el más reciente primero."""
    try:
        return servicios.listar_reportes_exogena(session, contador.id, contribuyente_id)
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc


@router.get(
    "/{contribuyente_id}/reportes-exogena/{reporte_exogena_id}/topes",
    response_model=List[TopeExogenaLeer],
)
def listar_topes(
    contribuyente_id: int,
    reporte_exogena_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Los cinco Topes del archivo (referencia informativa, Proceso 4)."""
    try:
        return servicios.listar_topes_exogena(
            session, contador.id, contribuyente_id, reporte_exogena_id
        )
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc


@router.get(
    "/{contribuyente_id}/reportes-exogena/{reporte_exogena_id}/registros",
    response_model=List[RegistroExogenaLeer],
)
def listar_registros(
    contribuyente_id: int,
    reporte_exogena_id: int,
    concepto_code: Optional[str] = None,
    nit_reportante: Optional[str] = None,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """HU-06, con los filtros opcionales que pide el criterio de aceptación."""
    try:
        return servicios.listar_registros_exogena(
            session,
            contador.id,
            contribuyente_id,
            reporte_exogena_id,
            concepto_code,
            nit_reportante,
        )
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc
