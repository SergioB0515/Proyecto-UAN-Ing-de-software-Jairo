from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalNoEncontradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from ..liquidacion.motor import AnioGravableNoSoportadoError
from . import informe, servicios
from .modelos import (
    DeclaracionAnteriorRegistrar,
    DeclaracionPresentadaLeer,
    DocumentoActualizar,
    DocumentoCrear,
    GestionLeer,
    PresentacionRegistrar,
    SeguimientoActualizar,
    SolicitudDocumentosLeer,
    TasaInteresDatos,
    TasaInteresMoratorio,
)

router = APIRouter(tags=["gestion"])

_BASE = "/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}"


def _traducir(exc: Exception) -> HTTPException:
    if isinstance(exc, (ContribuyenteNoEncontradoError, PeriodoFiscalNoEncontradoError,
                        servicios.DocumentoNoEncontradoError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (servicios.DatosInvalidosError, AnioGravableNoSoportadoError)):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


@router.get(f"{_BASE}/gestion", response_model=GestionLeer)
def ver_gestion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    fecha_pago: Optional[date] = Query(default=None),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Etapas, presentación, comparativo, firmeza, beneficio de auditoría,
    corrección e intereses de una declaración."""
    try:
        return servicios.gestion(session, contador.id, contribuyente_id,
                                 periodo_fiscal_id, fecha_pago)
    except Exception as exc:
        raise _traducir(exc)


@router.patch(f"{_BASE}/gestion/seguimiento", response_model=GestionLeer)
def actualizar_seguimiento_declaracion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    cambios: SeguimientoActualizar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.actualizar_seguimiento(session, contador.id, contribuyente_id,
                                         periodo_fiscal_id, cambios)
        return servicios.gestion(session, contador.id, contribuyente_id, periodo_fiscal_id)
    except Exception as exc:
        raise _traducir(exc)


@router.post(f"{_BASE}/gestion/presentaciones", response_model=DeclaracionPresentadaLeer,
             status_code=status.HTTP_201_CREATED)
def registrar_presentacion_declaracion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: PresentacionRegistrar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Guarda la declaración presentada (o su corrección) tal como está liquidada."""
    try:
        d = servicios.registrar_presentacion(session, contador.id, contribuyente_id,
                                             periodo_fiscal_id, datos)
        periodo = servicios.obtener_periodo_fiscal(session, contador.id,
                                                   contribuyente_id, periodo_fiscal_id)
        return servicios._leer_presentada(d, periodo.anio_gravable)
    except Exception as exc:
        raise _traducir(exc)


@router.post("/contribuyentes/{contribuyente_id}/declaraciones-anteriores",
             response_model=DeclaracionPresentadaLeer, status_code=status.HTTP_201_CREATED)
def registrar_declaracion_anterior(
    contribuyente_id: int,
    datos: DeclaracionAnteriorRegistrar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Registra a mano una declaración presentada que no se hizo en la app."""
    try:
        d = servicios.registrar_declaracion_anterior(session, contador.id,
                                                     contribuyente_id, datos)
        return servicios._leer_presentada(d, datos.anio_gravable)
    except Exception as exc:
        raise _traducir(exc)


@router.post(f"{_BASE}/gestion/traer-del-anio-anterior", response_model=List[str])
def traer_datos_del_anio_anterior(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Copia a la hoja el impuesto neto, el anticipo y el saldo a favor del año anterior."""
    try:
        return servicios.traer_datos_del_anio_anterior(
            session, contador.id, contribuyente_id, periodo_fiscal_id)
    except Exception as exc:
        raise _traducir(exc)


@router.get(f"{_BASE}/documentos", response_model=SolicitudDocumentosLeer)
def ver_solicitud_documentos(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.solicitud_documentos(session, contador.id, contribuyente_id,
                                              periodo_fiscal_id)
    except Exception as exc:
        raise _traducir(exc)


@router.patch(f"{_BASE}/documentos/{{clave}}", response_model=SolicitudDocumentosLeer)
def actualizar_documento_solicitado(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    clave: str,
    cambios: DocumentoActualizar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.actualizar_documento(session, contador.id, contribuyente_id,
                                              periodo_fiscal_id, clave, cambios)
    except Exception as exc:
        raise _traducir(exc)


@router.post(f"{_BASE}/documentos", response_model=SolicitudDocumentosLeer,
             status_code=status.HTTP_201_CREATED)
def agregar_documento_solicitado(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: DocumentoCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.agregar_documento(session, contador.id, contribuyente_id,
                                           periodo_fiscal_id, datos)
    except Exception as exc:
        raise _traducir(exc)


@router.get(f"{_BASE}/informe-cliente", response_class=Response)
def informe_para_el_cliente(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Informe de la declaración en PDF, escrito para el contribuyente."""
    try:
        contenido, nombre = informe.generar(session, contador, contribuyente_id,
                                            periodo_fiscal_id)
    except Exception as exc:
        raise _traducir(exc)
    return Response(content=contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/tasas-interes-moratorio", response_model=List[TasaInteresMoratorio])
def listar_tasas_interes(
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    return servicios.listar_tasas(session)


@router.put("/tasas-interes-moratorio", response_model=TasaInteresMoratorio)
def guardar_tasa_interes(
    datos: TasaInteresDatos,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    return servicios.guardar_tasa(session, datos)
