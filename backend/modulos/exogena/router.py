from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ArchivoExogenaInvalidoError,
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import servicios
from .modelos import RegistroExogenaLeer, ReporteExogenaLeer

router = APIRouter(prefix="/contribuyentes", tags=["exogena"])


@router.post(
    "/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/exogena",
    response_model=ReporteExogenaLeer,
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
    con la decisión de arquitectura del proyecto (documentacion/04-arquitectura.md)."""
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
    except (ContribuyenteNoEncontradoError, PeriodoFiscalNoEncontradoError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ArchivoExogenaInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


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
    except ContribuyenteNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
