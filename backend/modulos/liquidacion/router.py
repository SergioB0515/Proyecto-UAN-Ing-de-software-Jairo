from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.excepciones import (
    AnioGravableNoSoportadoError,
    ContribuyenteNoEncontradoError,
    DeduccionNoEncontradaError,
    FuenteIngresoNoEncontradaError,
    PeriodoFiscalNoEncontradoError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from . import clasificador, servicios
from ..reportes.exportacion import DocumentoReporte, Seccion, a_excel, a_pdf
from ..reportes.modelos import FormatoReporte
from ..reportes.servicios import _MEDIA_TYPES
from .modelos import (
    ClasificacionIngresoDatos,
    DeduccionSolicitadaCrear,
    DeduccionSolicitadaLeer,
    HojaLiquidacionActualizar,
    HojaLiquidacionLeer,
    IngresoClasificadoLeer,
    LiquidacionLeer,
)

router = APIRouter(prefix="/liquidacion", tags=["liquidacion"])

_BASE = "/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}"


def _traducir(exc: Exception) -> HTTPException:
    """Traduce los errores de dominio a códigos HTTP.

    `AnioGravableNoSoportadoError` es 422 y no 404: el periodo existe, lo que
    falta es que alguien cargue los parámetros de ese año. El mensaje dice
    dónde hacerlo, para que el error sea accionable y no un callejón.
    """
    if isinstance(exc, (ContribuyenteNoEncontradoError, PeriodoFiscalNoEncontradoError,
                        DeduccionNoEncontradaError, FuenteIngresoNoEncontradaError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, AnioGravableNoSoportadoError):
        # 422 literal: starlette renombró la constante y la versión antigua
        # emite DeprecationWarning, pero el código no cambia.
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


@router.get("/cedulas", response_model=List[dict])
def cedulas():
    """Catálogo de cédulas con lo que implica cada una. Alimenta el selector del frontend."""
    return clasificador.cedulas_disponibles()


@router.get(f"{_BASE}/hoja", response_model=HojaLiquidacionLeer)
def obtener_hoja(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.obtener_hoja(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)


@router.patch(f"{_BASE}/hoja", response_model=HojaLiquidacionLeer)
def actualizar_hoja(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: HojaLiquidacionActualizar,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.actualizar_hoja(
            session, contador.id, contribuyente_id, periodo_fiscal_id, datos
        )
    except Exception as exc:
        raise _traducir(exc)


@router.get(f"{_BASE}/deducciones", response_model=List[DeduccionSolicitadaLeer])
def listar_deducciones(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_deducciones(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)


@router.post(
    f"{_BASE}/deducciones",
    response_model=DeduccionSolicitadaLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_deduccion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: DeduccionSolicitadaCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.crear_deduccion(
            session, contador.id, contribuyente_id, periodo_fiscal_id, datos
        )
    except Exception as exc:
        raise _traducir(exc)


@router.delete(
    f"{_BASE}/deducciones/{{deduccion_id}}", status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_deduccion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    deduccion_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.eliminar_deduccion(
            session, contador.id, contribuyente_id, periodo_fiscal_id, deduccion_id
        )
    except Exception as exc:
        raise _traducir(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(f"{_BASE}/ingresos", response_model=List[IngresoClasificadoLeer])
def listar_ingresos(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_ingresos_clasificados(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)


@router.put(f"{_BASE}/ingresos", response_model=List[IngresoClasificadoLeer])
def clasificar_ingresos(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: List[ClasificacionIngresoDatos],
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.guardar_clasificaciones(
            session, contador.id, contribuyente_id, periodo_fiscal_id, datos
        )
    except Exception as exc:
        raise _traducir(exc)


@router.get(_BASE, response_model=LiquidacionLeer)
def liquidar(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.liquidar_periodo(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)


@router.get(f"{_BASE}/exportar", response_class=Response)
def exportar_liquidacion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    formato: FormatoReporte = FormatoReporte.XLSX,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Exporta el borrador con la fórmula y la norma de cada renglón.

    Se exporta la trazabilidad completa, no solo las cifras: el archivo tiene
    que servir como papel de trabajo frente a una revisión, y para eso cada
    número debe poder reconstruirse.
    """
    try:
        liq = servicios.liquidar_periodo(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)

    documento = DocumentoReporte(
        titulo="Borrador de liquidación — impuesto de renta personas naturales",
        encabezado=[
            f"Contribuyente ID {liq.contribuyente_id} — año gravable {liq.anio_gravable}",
            f"Régimen aplicado: {liq.parametros.regimen} — UVT ${liq.parametros.uvt}",
            f"Fuente de la UVT: {liq.parametros.fuente_uvt}",
        ],
        secciones=[
            Seccion(
                "Renglones",
                ["Código", "Concepto", "Valor calculado", "Valor a declarar", "Fórmula", "Fuente legal"],
                [
                    [r.codigo, r.nombre, float(r.valor), float(r.valor_declarable),
                     r.formula, r.fuente_legal]
                    for r in liq.renglones
                ],
            ),
            Seccion("Diagnósticos", [], [], liq.diagnosticos or ["Sin diagnósticos."]),
            Seccion("Notas y advertencias", [], [], liq.notas + [liq.advertencia]),
        ],
    )
    contenido = a_excel(documento) if formato == FormatoReporte.XLSX else a_pdf(documento)
    nombre = f"borrador_liquidacion_{liq.contribuyente_id}_{liq.anio_gravable}.{formato.value}"
    return Response(
        content=contenido,
        media_type=_MEDIA_TYPES[formato],
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
