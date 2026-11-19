from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ArchivoDemasiadoGrandeError,
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
    try:
        contenido = servicios.leer_archivo_exogena(archivo.file, archivo.filename)
        importado = servicios.importar_reporte_exogena(
            session,
            contador.id,
            contribuyente_id,
            periodo_fiscal_id,
            contenido,
            archivo.filename or "archivo.xlsx",
        )
        # Traducir el archivo a requerimientos en lenguaje común se hace aquí
        # y no en el servicio para no crear una dependencia circular: el
        # portal importa a exógena. El import es local por lo mismo.
        #
        # Está en el router del contador además del portal para que el camino
        # sea uno solo: cargue el archivo quien lo cargue, los requerimientos
        # quedan generados. Es idempotente.
        from modulos.portal.servicios import sincronizar_requerimientos

        reporte = servicios.obtener_reporte_exogena(
            session, contador.id, contribuyente_id, importado.id
        )
        sincronizar_requerimientos(session, reporte)
        return importado
    except _NO_ENCONTRADO as exc:
        raise _no_encontrado(exc) from exc
    except ArchivoDemasiadoGrandeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)
        ) from exc
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
