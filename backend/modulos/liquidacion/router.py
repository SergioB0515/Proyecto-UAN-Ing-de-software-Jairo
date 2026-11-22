from typing import List

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from core.dependencias import obtener_contador_actual
from core.formato import pesos
from core.excepciones import (
    ActivoNoEncontradoError,
    AnioGravableNoSoportadoError,
    ContribuyenteNoEncontradoError,
    DeduccionNoEncontradaError,
    FuenteIngresoNoEncontradaError,
    PagoEfectivoNoEncontradoError,
    PerdidaNoEncontradaError,
    PeriodoFiscalNoEncontradoError,
    PlantillaNoEncontradaError,
    SinPeriodoAnteriorError,
)
from database import obtener_sesion
from modulos.contadores.modelos import Contador

from ..contribuyentes.servicios import obtener_contribuyente
from . import clasificador, servicios
from . import borrador_210
from ..reportes.exportacion import DocumentoReporte, Seccion, a_excel, a_pdf
from ..reportes.modelos import FormatoReporte
from ..reportes.servicios import _MEDIA_TYPES
from .modelos import (
    VentaInmuebleCrear,
    VentaInmuebleLeer,
    DeduccionImputacion,
    EscenariosLeer,
    SimulacionAporteLeer,
    ClasificacionIngresoDatos,
    DatosDepreciacionGuardar,
    DatosDepreciacionLeer,
    PagoEfectivoCrear,
    PagoEfectivoLeer,
    PerdidaFiscalCrear,
    PerdidaFiscalLeer,
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
    """Errores de dominio -> HTTP. Año sin parámetros: 422."""
    if isinstance(exc, (ContribuyenteNoEncontradoError, PeriodoFiscalNoEncontradoError,
                        DeduccionNoEncontradaError, FuenteIngresoNoEncontradaError,
                        ActivoNoEncontradoError, PerdidaNoEncontradaError,
                        PagoEfectivoNoEncontradoError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    from core.excepciones import DatosVentaInvalidosError, VentaNoEncontradaError

    if isinstance(exc, VentaNoEncontradaError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, DatosVentaInvalidosError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (PlantillaNoEncontradaError, SinPeriodoAnteriorError)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, AnioGravableNoSoportadoError):
        # 422 literal: la constante de starlette cambió de nombre.
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


@router.get("/cedulas", response_model=List[dict])
def cedulas():
    """Catálogo de cédulas."""
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


@router.patch(
    f"{_BASE}/deducciones/{{deduccion_id}}", response_model=DeduccionSolicitadaLeer
)
def imputar_deduccion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    deduccion_id: int,
    datos: DeduccionImputacion,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Fija columna y fila del 210 de una deducción."""
    try:
        return servicios.imputar_deduccion(
            session, contador.id, contribuyente_id, periodo_fiscal_id, deduccion_id, datos
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
    """Exporta el borrador con fórmula y norma por renglón (papel de trabajo)."""
    try:
        liq = servicios.liquidar_periodo(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)

    # Encabezado con nombre y NIT, no el id interno.
    datos_contribuyente = obtener_contribuyente(session, contador.id, contribuyente_id)

    documento = DocumentoReporte(
        titulo="Borrador de liquidación — impuesto de renta personas naturales",
        encabezado=[
            f"{datos_contribuyente.nombre} — NIT {datos_contribuyente.rut}",
            f"Año gravable {liq.anio_gravable}",
            f"Régimen aplicado: {liq.parametros.regimen} — UVT {pesos(liq.parametros.uvt)}",
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


@router.get(f"{_BASE}/escenarios", response_model=EscenariosLeer)
def escenarios(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Escenarios: una decisión cambiada a la vez."""
    try:
        return servicios.simular_escenarios(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)


@router.get(f"{_BASE}/simulacion-aporte", response_model=SimulacionAporteLeer)
def simulacion_aporte(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    valor: Decimal = Query(gt=0, description="Aporte a simular, en pesos"),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Qué pasa con el impuesto si se aporta a un AFC o a pensión voluntaria.

    Es GET y no POST porque no guarda nada: reliquida en memoria y responde.
    """
    try:
        return servicios.simular_aporte_voluntario(
            session, contador.id, contribuyente_id, periodo_fiscal_id, valor
        )
    except Exception as exc:
        raise _traducir(exc)


@router.get(f"{_BASE}/formulario-210", response_class=Response)
def borrador_formulario_210(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Borrador del 210 en PDF, casilla por casilla, para transcribir."""
    try:
        liq = servicios.liquidar_periodo(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
        hoja = servicios.obtener_hoja(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)
    datos = obtener_contribuyente(session, contador.id, contribuyente_id)
    contenido = borrador_210.a_pdf(
        borrador_210.Borrador210(
            nombre=datos.nombre,
            nit=datos.rut,
            anio_gravable=liq.anio_gravable,
            casillas=borrador_210.construir_casillas(liq.renglones),
            marcadas=liq.casillas_marcadas,
            numero_dependientes=hoja.numero_dependientes,
            diagnosticos=liq.diagnosticos,
            notas=liq.notas,
        )
    )
    nombre = f"borrador_210_{datos.rut}_{liq.anio_gravable}.pdf"
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


# Depreciación


@router.get("/categorias-depreciacion", response_model=List[dict])
def categorias_depreciacion(
    anio_gravable: int = Query(ge=2000, le=2100),
    contador: Contador = Depends(obtener_contador_actual),
):
    """Catálogo del art. 137: tasa máxima y vida útil equivalente."""
    try:
        return servicios.categorias_depreciacion(anio_gravable)
    except Exception as exc:
        raise _traducir(exc)


@router.get(f"{_BASE}/depreciacion", response_model=List[DatosDepreciacionLeer])
def listar_depreciacion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_depreciacion(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)


@router.put(f"{_BASE}/depreciacion", response_model=List[DatosDepreciacionLeer])
def guardar_depreciacion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: List[DatosDepreciacionGuardar],
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.guardar_depreciacion(
            session, contador.id, contribuyente_id, periodo_fiscal_id, datos
        )
    except Exception as exc:
        raise _traducir(exc)


@router.delete(
    f"{_BASE}/depreciacion/{{activo_id}}", status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_depreciacion(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    activo_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.eliminar_depreciacion(
            session, contador.id, contribuyente_id, periodo_fiscal_id, activo_id
        )
    except Exception as exc:
        raise _traducir(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Pérdidas fiscales (por contribuyente)


@router.get(
    "/contribuyentes/{contribuyente_id}/perdidas", response_model=List[PerdidaFiscalLeer]
)
def listar_perdidas(
    contribuyente_id: int,
    anio_gravable: int = Query(ge=2000, le=2100),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Pérdidas del contribuyente y su vigencia en el año."""
    try:
        return servicios.listar_perdidas(
            session, contador.id, contribuyente_id, anio_gravable
        )
    except Exception as exc:
        raise _traducir(exc)


@router.post(
    "/contribuyentes/{contribuyente_id}/perdidas",
    response_model=PerdidaFiscalLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_perdida(
    contribuyente_id: int,
    datos: PerdidaFiscalCrear,
    anio_gravable: int = Query(ge=2000, le=2100),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.crear_perdida(session, contador.id, contribuyente_id, datos)
        creadas = servicios.listar_perdidas(
            session, contador.id, contribuyente_id, anio_gravable
        )
        return creadas[-1]
    except Exception as exc:
        raise _traducir(exc)


@router.delete(
    "/contribuyentes/{contribuyente_id}/perdidas/{perdida_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_perdida(
    contribuyente_id: int,
    perdida_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.eliminar_perdida(session, contador.id, contribuyente_id, perdida_id)
    except Exception as exc:
        raise _traducir(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Pagos en efectivo


@router.get(f"{_BASE}/pagos-efectivo", response_model=List[PagoEfectivoLeer])
def listar_pagos_efectivo(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_pagos_efectivo(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)


@router.post(
    f"{_BASE}/pagos-efectivo",
    response_model=PagoEfectivoLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_pago_efectivo(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: PagoEfectivoCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.crear_pago_efectivo(
            session, contador.id, contribuyente_id, periodo_fiscal_id, datos
        )
        return servicios.listar_pagos_efectivo(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )[-1]
    except Exception as exc:
        raise _traducir(exc)


@router.delete(
    f"{_BASE}/pagos-efectivo/{{pago_id}}", status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_pago_efectivo(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    pago_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.eliminar_pago_efectivo(
            session, contador.id, contribuyente_id, periodo_fiscal_id, pago_id
        )
    except Exception as exc:
        raise _traducir(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Facilidades


@router.get(f"{_BASE}/plantillas-deducciones", response_model=List[dict])
def plantillas_deducciones(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Deducciones frecuentes con norma y tope en pesos."""
    try:
        return servicios.catalogo_plantillas(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)


@router.post(
    f"{_BASE}/deducciones/desde-plantilla",
    response_model=DeduccionSolicitadaLeer,
    status_code=status.HTTP_201_CREATED,
)
def crear_deduccion_desde_plantilla(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    codigo: str = Query(min_length=1, max_length=60),
    valor: Decimal = Query(ge=0),
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.crear_deduccion_desde_plantilla(
            session, contador.id, contribuyente_id, periodo_fiscal_id, codigo, valor
        )
    except Exception as exc:
        raise _traducir(exc)


@router.post(f"{_BASE}/hoja/copiar-del-anterior", response_model=HojaLiquidacionLeer)
def copiar_hoja_del_anterior(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Copia del año anterior la situación, no las cifras."""
    try:
        return servicios.copiar_hoja_del_anio_anterior(
            session, contador.id, contribuyente_id, periodo_fiscal_id
        )
    except Exception as exc:
        raise _traducir(exc)



# Venta de inmuebles


@router.get(f"{_BASE}/ventas-inmuebles", response_model=List[VentaInmuebleLeer])
def listar_ventas_inmuebles(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        return servicios.listar_ventas_inmuebles(session, contador.id, contribuyente_id,
                                                 periodo_fiscal_id)
    except Exception as exc:
        raise _traducir(exc)


@router.post(f"{_BASE}/ventas-inmuebles", response_model=VentaInmuebleLeer,
             status_code=status.HTTP_201_CREATED)
def crear_venta_inmueble(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: VentaInmuebleCrear,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    """Registra una venta de inmueble: costo fiscal (arts. 69, 72, 73), utilidad
    y tratamiento (art. 300).
    """
    try:
        return servicios.crear_venta_inmueble(session, contador.id, contribuyente_id,
                                              periodo_fiscal_id, datos)
    except Exception as exc:
        raise _traducir(exc)


@router.delete(f"{_BASE}/ventas-inmuebles/{{venta_id}}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_venta_inmueble(
    contribuyente_id: int,
    periodo_fiscal_id: int,
    venta_id: int,
    contador: Contador = Depends(obtener_contador_actual),
    session: Session = Depends(obtener_sesion),
):
    try:
        servicios.eliminar_venta_inmueble(session, contador.id, contribuyente_id,
                                          periodo_fiscal_id, venta_id)
    except Exception as exc:
        raise _traducir(exc)
