"""Cierre de periodo fiscal (HU-15), reportes exportables (HU-16) y resumen
por contribuyente (HU-17). Procesos 10 y 11 de
documentacion/03-logica-proyecto.md.
"""
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from core.excepciones import (
    EstadoPeriodoInvalidoError,
    ReporteExogenaNoEncontradoError,
    UmbralNoConfiguradoError,
)

from ..conciliacion.modelos import EstadoConciliacion
from ..conciliacion.servicios import conciliar_contribuyente, generar_borrador_renglones
from ..contribuyentes.modelos import (
    Activo,
    EstadoPeriodo,
    PeriodoFiscal,
    TipoActivo,
)
from ..contribuyentes.servicios import (
    activos_vigentes,
    listar_fuentes_ingreso,
    obtener_contribuyente,
    obtener_periodo_fiscal,
)
from ..inventario.servicios import TIPOS_CON_INVENTARIO, obtener_contribuyente_con_inventario
from ..movimientos.servicios import calcular_costo_ventas, kardex_por_periodo
from ..parametros.modelos import ResultadoObligacion
from ..parametros.servicios import verificar_obligacion_declarar
from .exportacion import DocumentoReporte, Seccion, a_excel, a_pdf
from .modelos import (
    CierrePeriodo,
    CierrePeriodoLeer,
    FormatoReporte,
    ResumenContribuyente,
    ResumenIngresos,
    ResumenInventario,
    ResumenPatrimonio,
    TipoReporte,
)

AVISO_SIN_PERIODO_EN_ACTIVOS = (
    "Los activos y fuentes de ingreso no están asociados a un periodo: se "
    "muestran los registrados a la fecha."
)

# --------------------------------------------------------------- Cierre (HU-15)


def _a_leer(cierre: CierrePeriodo, periodo: PeriodoFiscal) -> CierrePeriodoLeer:
    return CierrePeriodoLeer(
        **cierre.model_dump(), anio_gravable=periodo.anio_gravable, estado=periodo.estado
    )


def cerrar_periodo(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> CierrePeriodoLeer:
    """Proceso 10:
    1. El periodo debe estar ABIERTO y todos los años anteriores cerrados
       (el saldo inicial de un año depende del cierre del anterior).
    2. Si el contribuyente maneja inventario, el saldo final valorizado se
       registra como un Activo INVENTARIO (aunque valga 0, para que el
       patrimonio deje de contar el inventario del año anterior).
    3. El periodo pasa a CERRADO: ya no admite movimientos ni exógena.
    """
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    if periodo.estado == EstadoPeriodo.CERRADO:
        raise EstadoPeriodoInvalidoError(f"El periodo {periodo.anio_gravable} ya está cerrado")

    anteriores_abiertos = session.exec(
        select(PeriodoFiscal.anio_gravable).where(
            PeriodoFiscal.contribuyente_id == contribuyente_id,
            PeriodoFiscal.anio_gravable < periodo.anio_gravable,
            PeriodoFiscal.estado == EstadoPeriodo.ABIERTO,
        )
    ).all()
    if anteriores_abiertos:
        anios = ", ".join(str(a) for a in sorted(anteriores_abiertos))
        raise EstadoPeriodoInvalidoError(
            f"Antes de cerrar {periodo.anio_gravable} hay que cerrar: {anios}"
        )

    cierre = CierrePeriodo(periodo_fiscal_id=periodo.id, contribuyente_id=contribuyente_id)
    if contribuyente.tipo_contribuyente in TIPOS_CON_INVENTARIO:
        costo = calcular_costo_ventas(session, contador_id, contribuyente_id, periodo.id)
        activo = Activo(
            descripcion=f"Inventario de mercancía al 31/12/{periodo.anio_gravable}",
            tipo=TipoActivo.INVENTARIO,
            valor=costo.total_inventario_final,
            contribuyente_id=contribuyente_id,
        )
        session.add(activo)
        session.flush()
        cierre.valor_inventario = costo.total_inventario_final
        cierre.costo_ventas = costo.total_costo_ventas
        cierre.activo_inventario_id = activo.id

    periodo.estado = EstadoPeriodo.CERRADO
    session.add(cierre)
    session.add(periodo)
    session.commit()
    session.refresh(cierre)
    session.refresh(periodo)
    return _a_leer(cierre, periodo)


def reabrir_periodo(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> PeriodoFiscal:
    """Deshace un cierre para corregir algo: borra el Activo INVENTARIO que
    creó y vuelve el periodo a ABIERTO. Solo se puede reabrir el último año
    cerrado, para no invalidar el saldo inicial de un año posterior."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    if periodo.estado == EstadoPeriodo.ABIERTO:
        raise EstadoPeriodoInvalidoError(f"El periodo {periodo.anio_gravable} no está cerrado")

    posteriores_cerrados = session.exec(
        select(PeriodoFiscal.anio_gravable).where(
            PeriodoFiscal.contribuyente_id == contribuyente_id,
            PeriodoFiscal.anio_gravable > periodo.anio_gravable,
            PeriodoFiscal.estado == EstadoPeriodo.CERRADO,
        )
    ).all()
    if posteriores_cerrados:
        anios = ", ".join(str(a) for a in sorted(posteriores_cerrados))
        raise EstadoPeriodoInvalidoError(
            f"Antes de reabrir {periodo.anio_gravable} hay que reabrir: {anios}"
        )

    cierre = session.get(CierrePeriodo, periodo.id)
    if cierre is not None:
        activo = (
            session.get(Activo, cierre.activo_inventario_id)
            if cierre.activo_inventario_id is not None
            else None
        )
        session.delete(cierre)
        session.flush()
        if activo is not None:
            session.delete(activo)

    periodo.estado = EstadoPeriodo.ABIERTO
    session.add(periodo)
    session.commit()
    session.refresh(periodo)
    return periodo


# -------------------------------------------------------------- Resumen (HU-17)


def evaluar_declaracion(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> Tuple[Optional[ResultadoObligacion], Optional[Dict[EstadoConciliacion, int]], List[str]]:
    """Obligación de declarar y resumen de conciliación de un periodo, sin
    fallar si todavía falta la exógena o el umbral: en ese caso devuelve
    None y el motivo en avisos. Lo usan el resumen y el panel de cartera."""
    avisos: List[str] = []
    obligacion = None
    conciliacion = None
    try:
        obligacion = verificar_obligacion_declarar(
            session, contador_id, contribuyente_id, periodo_fiscal_id
        )
    except ReporteExogenaNoEncontradoError:
        avisos.append("Aún no se ha importado la exógena de este periodo.")
    except UmbralNoConfiguradoError as exc:
        avisos.append(f"{exc}: no se puede evaluar la obligación de declarar.")

    try:
        conciliacion = conciliar_contribuyente(
            session, contador_id, contribuyente_id, periodo_fiscal_id
        ).resumen
    except ReporteExogenaNoEncontradoError:
        pass  # el aviso ya quedó registrado arriba

    return obligacion, conciliacion, avisos


def construir_resumen(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> ResumenContribuyente:
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)

    activos = activos_vigentes(session, contador_id, contribuyente_id)
    por_tipo: Dict[str, float] = defaultdict(float)
    for activo in activos:
        por_tipo[activo.tipo.value] += activo.valor

    fuentes = listar_fuentes_ingreso(session, contador_id, contribuyente_id)

    inventario = None
    if contribuyente.tipo_contribuyente in TIPOS_CON_INVENTARIO:
        costo = calcular_costo_ventas(session, contador_id, contribuyente_id, periodo.id)
        inventario = ResumenInventario(
            cantidad_productos=len(costo.productos),
            total_ingresos_ventas=costo.total_ingresos_ventas,
            total_costo_ventas=costo.total_costo_ventas,
            total_utilidad_bruta=costo.total_utilidad_bruta,
            inventario_final=costo.total_inventario_final,
        )

    obligacion, conciliacion, avisos = evaluar_declaracion(
        session, contador_id, contribuyente_id, periodo.id
    )
    cierre = session.get(CierrePeriodo, periodo.id)

    return ResumenContribuyente(
        contribuyente_id=contribuyente.id,
        nombre=contribuyente.nombre,
        rut=contribuyente.rut,
        tipo_contribuyente=contribuyente.tipo_contribuyente,
        regimen_tributario=contribuyente.regimen_tributario,
        periodo_fiscal_id=periodo.id,
        anio_gravable=periodo.anio_gravable,
        estado_periodo=periodo.estado,
        cierre=_a_leer(cierre, periodo) if cierre is not None else None,
        patrimonio=ResumenPatrimonio(
            patrimonio_liquido=round(sum(a.valor for a in activos), 2),
            por_tipo=dict(por_tipo),
        ),
        ingresos=ResumenIngresos(
            cantidad_fuentes=len(fuentes),
            total_ingresos=round(sum(f.valor_anual for f in fuentes), 2),
            total_retenciones=round(sum(f.retencion_fuente for f in fuentes), 2),
        ),
        inventario=inventario,
        obligacion=obligacion,
        conciliacion=conciliacion,
        avisos=[AVISO_SIN_PERIODO_EN_ACTIVOS] + avisos,
    )


# -------------------------------------------------- Reportes exportables (HU-16)

_TITULOS = {
    TipoReporte.KARDEX: "Kardex de inventario",
    TipoReporte.SALDO_INVENTARIO: "Saldo de inventario y costo de ventas",
    TipoReporte.CONCILIACION: "Reporte de conciliación de información exógena",
    TipoReporte.BORRADOR_RENGLONES: "Borrador de valores sugeridos por renglón",
    TipoReporte.RESUMEN: "Resumen del contribuyente",
}

_MEDIA_TYPES = {
    FormatoReporte.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FormatoReporte.PDF: "application/pdf",
}


def generar_reporte(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    tipo: TipoReporte,
    formato: FormatoReporte,
) -> Tuple[bytes, str, str]:
    """Devuelve (contenido, media_type, nombre_de_archivo)."""
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)

    constructores = {
        TipoReporte.KARDEX: _secciones_kardex,
        TipoReporte.SALDO_INVENTARIO: _secciones_saldo_inventario,
        TipoReporte.CONCILIACION: _secciones_conciliacion,
        TipoReporte.BORRADOR_RENGLONES: _secciones_borrador,
        TipoReporte.RESUMEN: _secciones_resumen,
    }
    secciones = constructores[tipo](session, contador_id, contribuyente_id, periodo.id)

    documento = DocumentoReporte(
        titulo=_TITULOS[tipo],
        encabezado=[
            f"Contribuyente: {contribuyente.nombre} — RUT {contribuyente.rut}",
            f"Año gravable: {periodo.anio_gravable} (periodo {periodo.estado.value})",
            f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ],
        secciones=secciones,
    )
    contenido = a_excel(documento) if formato == FormatoReporte.XLSX else a_pdf(documento)
    nombre = f"{tipo.value}_{contribuyente.rut}_{periodo.anio_gravable}.{formato.value}"
    return contenido, _MEDIA_TYPES[formato], nombre


def _secciones_kardex(session, contador_id, contribuyente_id, periodo_id) -> List[Seccion]:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    columnas = [
        "Fecha", "Movimiento", "Tipo", "Cantidad", "Costo unitario", "Costo total",
        "Precio venta", "Saldo cantidad", "Saldo valor",
    ]
    secciones = []
    for k in kardex_por_periodo(session, contador_id, contribuyente_id, periodo_id):
        filas: List[list] = [
            ["", "", "Saldo inicial", None, None, None, None,
             k.saldo_inicial_cantidad, k.saldo_inicial_valor]
        ]
        filas += [
            [l.fecha, l.movimiento_id, l.tipo.value, l.cantidad, l.costo_unitario,
             l.costo_total, l.precio_venta_unitario, l.saldo_cantidad, l.saldo_valor]
            for l in k.lineas
        ]
        filas.append(
            ["", "", "Saldo final", None, None, None, None,
             k.saldo_final_cantidad, k.saldo_final_valor]
        )
        secciones.append(
            Seccion(
                titulo=f"{k.codigo} — {k.nombre} ({k.metodo_costeo.value})",
                columnas=columnas,
                filas=filas,
            )
        )
    if not secciones:
        secciones.append(
            Seccion("Sin movimientos", [], [], ["No hay movimientos ni saldo en este periodo."])
        )
    return secciones


def _secciones_saldo_inventario(session, contador_id, contribuyente_id, periodo_id) -> List[Seccion]:
    costo = calcular_costo_ventas(session, contador_id, contribuyente_id, periodo_id)
    saldos = [
        [p.codigo, p.nombre, p.metodo_costeo.value, p.saldo_final_cantidad,
         round(p.saldo_final_valor / p.saldo_final_cantidad, 2) if p.saldo_final_cantidad else None,
         p.saldo_final_valor]
        for p in costo.productos
    ]
    saldos.append(["", "TOTAL", "", None, None, costo.total_inventario_final])
    ventas = [
        [p.codigo, p.nombre, p.cantidad_vendida, p.ingresos_ventas, p.costo_ventas, p.utilidad_bruta]
        for p in costo.productos
    ]
    ventas.append(
        ["", "TOTAL", None, costo.total_ingresos_ventas, costo.total_costo_ventas,
         costo.total_utilidad_bruta]
    )
    return [
        Seccion(
            "Saldo de inventario al cierre del año",
            ["Código", "Producto", "Método", "Cantidad", "Costo unitario", "Valor"],
            saldos,
        ),
        Seccion(
            "Costo de ventas del periodo",
            ["Código", "Producto", "Cantidad vendida", "Ingresos", "Costo de ventas", "Utilidad bruta"],
            ventas,
        ),
    ]


def _secciones_conciliacion(session, contador_id, contribuyente_id, periodo_id) -> List[Seccion]:
    resultado = conciliar_contribuyente(session, contador_id, contribuyente_id, periodo_id)
    return [
        Seccion(
            "Detalle por concepto",
            ["Concepto", "Origen", "Tercero", "Concepto DIAN", "Valor declarado",
             "Valor exógena", "Diferencia", "Estado"],
            [
                [i.concepto, i.origen.value, i.nombre_reportante, i.concepto_code,
                 i.valor_declarado, i.valor_exogena, i.diferencia, i.estado.value]
                for i in resultado.items
            ],
        ),
        Seccion(
            "Resumen por estado",
            ["Estado", "Cantidad"],
            [[estado.value, cantidad] for estado, cantidad in resultado.resumen.items()],
            [
                "NO_DECLARADO: aparece en la exógena y no hay nada registrado que lo "
                "explique (mayor riesgo). Se excluyen filas autoreportadas, de la "
                "DIAN y de retención."
            ],
        ),
    ]


def _secciones_borrador(session, contador_id, contribuyente_id, periodo_id) -> List[Seccion]:
    borrador = generar_borrador_renglones(session, contador_id, contribuyente_id, periodo_id)
    return [
        Seccion(
            "Valores sugeridos",
            ["Renglón", "Valor sugerido", "Registros"],
            [[r.renglon, r.valor_total, r.cantidad_registros] for r in borrador.renglones],
            [borrador.advertencia],
        )
    ]


def _secciones_resumen(session, contador_id, contribuyente_id, periodo_id) -> List[Seccion]:
    r = construir_resumen(session, contador_id, contribuyente_id, periodo_id)
    secciones = [
        Seccion(
            "Datos generales",
            ["Campo", "Valor"],
            [
                ["Tipo de contribuyente", r.tipo_contribuyente.value],
                ["Régimen tributario", r.regimen_tributario],
                ["Estado del periodo", r.estado_periodo.value],
                ["Patrimonio líquido", r.patrimonio.patrimonio_liquido],
                ["Ingresos registrados", r.ingresos.total_ingresos],
                ["Retenciones en la fuente", r.ingresos.total_retenciones],
            ],
        ),
        Seccion(
            "Patrimonio por tipo de activo",
            ["Tipo", "Valor"],
            [[tipo, valor] for tipo, valor in sorted(r.patrimonio.por_tipo.items())],
        ),
    ]
    if r.inventario is not None:
        secciones.append(
            Seccion(
                "Inventario",
                ["Campo", "Valor"],
                [
                    ["Productos con movimiento o saldo", r.inventario.cantidad_productos],
                    ["Ingresos por ventas", r.inventario.total_ingresos_ventas],
                    ["Costo de ventas", r.inventario.total_costo_ventas],
                    ["Utilidad bruta", r.inventario.total_utilidad_bruta],
                    ["Inventario final", r.inventario.inventario_final],
                ],
            )
        )
    if r.obligacion is not None:
        secciones.append(
            Seccion(
                "Obligación de declarar: " + ("SÍ OBLIGADO" if r.obligacion.obligado else "NO OBLIGADO"),
                ["Criterio", "Valor reportado", "Umbral", "Supera"],
                [[c.criterio, c.valor_reportado, c.umbral, c.supera_umbral] for c in r.obligacion.criterios],
                [r.obligacion.advertencia],
            )
        )
    if r.conciliacion is not None:
        secciones.append(
            Seccion(
                "Conciliación",
                ["Estado", "Cantidad"],
                [[estado.value, cantidad] for estado, cantidad in r.conciliacion.items()],
            )
        )
    secciones.append(Seccion("Avisos", [], [], r.avisos))
    return secciones
