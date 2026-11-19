"""El portal del contribuyente: todo lo que un token permite hacer.

Está en un archivo aparte para que el alcance del enlace se pueda auditar
leyendo un solo archivo corto. Tres propiedades que se sostienen a la vista:

1. **Ninguna ruta depende de `obtener_contador_actual`.** Quien abre el enlace
   no tiene cuenta y no necesita una.
2. **El alcance lo fija el token, no el cliente.** Ninguna ruta recibe un
   `contribuyente_id` ni un `periodo_fiscal_id`: salen del enlace resuelto.
   Por eso no existe el parámetro que habría que validar.
3. **Ninguna respuesta lleva la liquidación.** Eso ya no se puede afirmar por
   los imports —la lista de documentos viene de `gestion`, que sí lee la
   liquidación para saber qué pedir—, así que lo verifica una prueba que
   recorre el esquema de todas las respuestas de este router.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlmodel import Session

from core.excepciones import (
    AdjuntoDuplicadoError,
    AnioGravableNoSoportadoError,
    ArchivoDemasiadoGrandeError,
    ArchivoExogenaInvalidoError,
    ArchivoNoPermitidoError,
    DatoAdicionalNoEncontradoError,
    EnlaceCargaExpiradoError,
    EnlaceCargaNoEncontradoError,
    EnlaceCargaRevocadoError,
    IdentidadNoCoincideError,
    PeriodoFiscalCerradoError,
    PoliticaNoAceptadaError,
    TopeAdicionalExcedidoError,
    VersionPoliticaDesconocidaError,
)
from database import obtener_sesion

from ..adjuntos.modelos import AdjuntoLeer
from ..exogena.servicios import leer_archivo_exogena
from ..gestion.modelos import DocumentoActualizar, DocumentoLeer
from ..gestion.servicios import DocumentoNoEncontradoError
from . import servicios
from .modelos import (
    AceptarPolitica,
    AutorizacionLeer,
    DatoAdicionalCrear,
    DatoAdicionalLeer,
    EnlaceCarga,
    ParametrosAdicionales,
    ResultadoCargaExogena,
    SesionPortal,
)

router = APIRouter(prefix="/carga", tags=["portal público"])


def _traducir(exc: Exception) -> HTTPException:
    if isinstance(exc, EnlaceCargaNoEncontradoError):
        codigo = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (EnlaceCargaRevocadoError, EnlaceCargaExpiradoError)):
        # 410: el enlace existió y ya no sirve. Es distinto de «no existe» y
        # le permite al portal mostrar «pida uno nuevo» en vez de «no encontrado».
        codigo = status.HTTP_410_GONE
    elif isinstance(exc, (DocumentoNoEncontradoError, DatoAdicionalNoEncontradoError)):
        codigo = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ArchivoDemasiadoGrandeError):
        codigo = status.HTTP_413_CONTENT_TOO_LARGE
    elif isinstance(exc, ArchivoNoPermitidoError):
        codigo = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif isinstance(
        exc,
        (
            ArchivoExogenaInvalidoError,
            TopeAdicionalExcedidoError,
            IdentidadNoCoincideError,
        ),
    ):
        codigo = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        codigo = status.HTTP_409_CONFLICT
    return HTTPException(status_code=codigo, detail=str(exc))


_ERRORES = (
    EnlaceCargaNoEncontradoError,
    EnlaceCargaRevocadoError,
    EnlaceCargaExpiradoError,
    PoliticaNoAceptadaError,
    VersionPoliticaDesconocidaError,
    IdentidadNoCoincideError,
    DocumentoNoEncontradoError,
    DatoAdicionalNoEncontradoError,
    TopeAdicionalExcedidoError,
    AnioGravableNoSoportadoError,
    PeriodoFiscalCerradoError,
    ArchivoDemasiadoGrandeError,
    ArchivoExogenaInvalidoError,
    ArchivoNoPermitidoError,
    AdjuntoDuplicadoError,
)


def enlace_del_token(
    token: str, session: Session = Depends(obtener_sesion)
) -> EnlaceCarga:
    """Resuelve el token y deja el enlace disponible para la ruta.

    Una sola dependencia para todas las rutas: no hay forma de agregar un
    endpoint al portal y olvidarse de validar el enlace, porque sin ella no
    se tiene a qué contribuyente escribir.
    """
    try:
        return servicios.resolver_enlace(session, token)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


def _red_de_origen(request: Request) -> Optional[str]:
    """Prefijo de red de quien acepta, como respaldo de la autorización.

    Se guarda el prefijo y no la dirección completa: alcanza para sostener
    que la aceptación vino de una conexión concreta sin almacenar un dato
    personal más preciso del necesario.

    No se lee `X-Forwarded-For`: es un encabezado que el cliente puede
    escribir, así que respaldar una autorización con él no respalda nada.
    Detrás de un proxy esto registra la red del proxy, y eso es honesto.
    """
    host = request.client.host if request.client else None
    if not host:
        return None
    if ":" in host:
        return ":".join(host.split(":")[:4]) + "::/64"
    partes = host.split(".")
    if len(partes) == 4:
        return ".".join(partes[:3]) + ".0/24"
    return None


@router.get("/{token}", response_model=SesionPortal)
def abrir_portal(
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    """Lo que ve el contribuyente al abrir el enlace.

    Reanudable: si ya había entrado, vuelve a encontrar sus respuestas y sus
    archivos tal como los dejó. El enlace no se consume al usarlo.
    """
    return servicios.sesion_portal(session, enlace)


@router.post(
    "/{token}/politica",
    response_model=AutorizacionLeer,
    status_code=status.HTTP_201_CREATED,
)
def aceptar_politica(
    datos: AceptarPolitica,
    request: Request,
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.aceptar_politica(
            session,
            enlace,
            datos,
            red_origen=_red_de_origen(request),
            agente_usuario=request.headers.get("user-agent"),
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.post(
    "/{token}/exogena",
    response_model=ResultadoCargaExogena,
    status_code=status.HTTP_201_CREATED,
)
def cargar_exogena(
    archivo: UploadFile = File(...),
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    """Recibe el Excel que el contribuyente descargó del portal de la DIAN."""
    try:
        contenido = leer_archivo_exogena(archivo.file, archivo.filename)
        return servicios.cargar_exogena_por_enlace(
            session, enlace, contenido, archivo.filename or "exogena.xlsx"
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get("/{token}/documentos", response_model=List[DocumentoLeer])
def listar_documentos(
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    """Los documentos que se le piden. Es la misma lista que ve el contador."""
    return servicios.documentos_del_enlace(session, enlace)


@router.patch("/{token}/documentos/{clave}", response_model=DocumentoLeer)
def responder_documento(
    clave: str,
    cambios: DocumentoActualizar,
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    """Marca el estado del documento. El estado es obligatorio; el valor, no."""
    try:
        return servicios.responder_documento_por_enlace(
            session, enlace, clave, cambios
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.post(
    "/{token}/documentos/{clave}/archivos",
    response_model=AdjuntoLeer,
    status_code=status.HTTP_201_CREATED,
)
def subir_soporte(
    clave: str,
    archivo: UploadFile = File(...),
    descripcion: Optional[str] = Form(None, max_length=300),
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    """Sube una foto o un PDF desde el celular, sin cuenta de usuario.

    Subir el papel deja el documento en RECIBIDO: no hace falta marcar nada
    más después.
    """
    try:
        return servicios.adjuntar_por_enlace(
            session, enlace, clave, archivo.file, archivo.filename, descripcion
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get("/{token}/adicionales/parametros", response_model=ParametrosAdicionales)
def parametros_adicionales(
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    """Los topes del año gravable, para que el formulario los muestre.

    Salen de la misma tabla versionada que usa el servidor para validar: lo
    que el contribuyente ve en pantalla y lo que el servidor acepta no pueden
    separarse, porque son el mismo dato.
    """
    periodo = servicios.periodo_del_enlace(session, enlace)
    try:
        return servicios.parametros_adicionales(periodo.anio_gravable)
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.get("/{token}/adicionales", response_model=List[DatoAdicionalLeer])
def listar_adicionales(
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    return servicios.listar_adicionales(
        session, enlace.contribuyente_id, enlace.periodo_fiscal_id
    )


@router.post(
    "/{token}/adicionales",
    response_model=DatoAdicionalLeer,
    status_code=status.HTTP_201_CREATED,
)
def agregar_adicional(
    datos: DatoAdicionalCrear,
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    """Formulario controlado: solo los conceptos del catálogo del año."""
    try:
        servicios.exigir_politica_aceptada(session, enlace)
        return servicios.agregar_adicional(
            session, enlace.contribuyente_id, enlace.periodo_fiscal_id, datos,
            capturado_en_portal=True,
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc


@router.delete(
    "/{token}/adicionales/{adicional_id}", status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_adicional(
    adicional_id: int,
    enlace: EnlaceCarga = Depends(enlace_del_token),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.exigir_politica_aceptada(session, enlace)
        servicios.eliminar_adicional(
            session, enlace.contribuyente_id, enlace.periodo_fiscal_id, adicional_id
        )
    except _ERRORES as exc:
        raise _traducir(exc) from exc
