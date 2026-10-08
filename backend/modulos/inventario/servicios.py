from typing import List

from sqlmodel import Session, select

from core.excepciones import PeriodoFiscalNoEncontradoError, ReporteExogenaNoEncontradoError

from ..contribuyentes.modelos import Activo, FuenteIngreso, PeriodoFiscal
from ..contribuyentes.servicios import listar_activos, listar_fuentes_ingreso, obtener_contribuyente
from ..exogena.modelos import RegistroExogena, ReporteExogena
from .modelos import BorradorRenglones, ItemConciliacion, RenglonSugerido, ResultadoConciliacion

CONCEPTO_CONSUMO_TC = "1023"


def _obtener_periodo_validado(session, contribuyente_id, periodo_fiscal_id):
    periodo = session.get(PeriodoFiscal, periodo_fiscal_id)
    if periodo is None or periodo.contribuyente_id != contribuyente_id:
        raise PeriodoFiscalNoEncontradoError(
            f"No existe el periodo fiscal {periodo_fiscal_id} para el contribuyente {contribuyente_id}"
        )
    return periodo


def _obtener_reporte_mas_reciente(session, periodo_fiscal_id):
    reporte = session.exec(
        select(ReporteExogena)
        .where(ReporteExogena.periodo_fiscal_id == periodo_fiscal_id)
        .order_by(ReporteExogena.fecha_importacion.desc())
    ).first()
    if reporte is None:
        raise ReporteExogenaNoEncontradoError(
            f"No se ha importado la exógena del periodo fiscal {periodo_fiscal_id}"
        )
    return reporte


def conciliar_contribuyente(session, contador_id, contribuyente_id, periodo_fiscal_id):
    obtener_contribuyente(session, contador_id, contribuyente_id)
    _obtener_periodo_validado(session, contribuyente_id, periodo_fiscal_id)
    reporte = _obtener_reporte_mas_reciente(session, periodo_fiscal_id)

    registros_exogena = session.exec(
        select(RegistroExogena).where(RegistroExogena.reporte_exogena_id == reporte.id)
    ).all()

    activos = listar_activos(session, contador_id, contribuyente_id)
    fuentes_ingreso = listar_fuentes_ingreso(session, contador_id, contribuyente_id)

    items_conciliacion = []
    ids_registros_usados = set()

    declarados = []
    for activo in activos:
        declarados.append({
            "concepto": activo.descripcion,
            "valor_declarado": activo.valor,
            "vinculo_codigo_concepto": activo.vinculo_codigo_concepto,
            "vinculo_palabra_clave": activo.vinculo_palabra_clave,
            "origen": "Activo",
        })
    for fuente in fuentes_ingreso:
        declarados.append({
            "concepto": fuente.concepto,
            "valor_declarado": fuente.valor_anual,
            "vinculo_codigo_concepto": fuente.vinculo_codigo_concepto,
            "vinculo_palabra_clave": fuente.vinculo_palabra_clave,
            "origen": "FuenteIngreso",
        })

    for dec in declarados:
        match = None
        if dec["vinculo_codigo_concepto"]:
            for reg in registros_exogena:
                if reg.id not in ids_registros_usados and reg.concepto_code == dec["vinculo_codigo_concepto"]:
                    match = reg
                    break
        if not match and dec["vinculo_palabra_clave"]:
            palabra_clave = dec["vinculo_palabra_clave"].lower()
            for reg in registros_exogena:
                if reg.id not in ids_registros_usados and reg.detalle and palabra_clave in reg.detalle.lower():
                    match = reg
                    break

        if match:
            ids_registros_usados.add(match.id)
            diferencia = match.valor - dec["valor_declarado"]
            tolerancia = max(1000, match.valor * 0.005)
            estado = "COINCIDE" if abs(diferencia) <= tolerancia else "DISCREPANCIA"
            items_conciliacion.append(
                ItemConciliacion(
                    concepto=dec["concepto"],
                    origen=dec["origen"],
                    valor_declarado=dec["valor_declarado"],
                    valor_exogena=match.valor,
                    diferencia=diferencia,
                    estado=estado
                )
            )
        else:
            items_conciliacion.append(
                ItemConciliacion(
                    concepto=dec["concepto"],
                    origen=dec["origen"],
                    valor_declarado=dec["valor_declarado"],
                    valor_exogena=None,
                    diferencia=None,
                    estado="NO_REPORTADO_POR_TERCERO"
                )
            )

    for reg in registros_exogena:
        if reg.id in ids_registros_usados:
            continue
        if (reg.es_auto_reportado or
            reg.es_dian or
            reg.concepto_code == CONCEPTO_CONSUMO_TC or
            (reg.detalle and "retenci" in reg.detalle.lower())):
            continue
        items_conciliacion.append(
            ItemConciliacion(
                concepto=reg.detalle,
                origen="Exógena",
                valor_declarado=None,
                valor_exogena=reg.valor,
                diferencia=None,
                estado="NO_DECLARADO"
            )
        )

    return ResultadoConciliacion(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        items=items_conciliacion
    )


def generar_borrador_renglones(session, contador_id, contribuyente_id, periodo_fiscal_id):
    obtener_contribuyente(session, contador_id, contribuyente_id)
    _obtener_periodo_validado(session, contribuyente_id, periodo_fiscal_id)
    reporte = _obtener_reporte_mas_reciente(session, periodo_fiscal_id)

    registros_exogena = session.exec(
        select(RegistroExogena).where(RegistroExogena.reporte_exogena_id == reporte.id)
    ).all()

    acumulados_renglones = {}
    for reg in registros_exogena:
        if reg.renglones_sugeridos:
            renglones = [r.strip() for r in reg.renglones_sugeridos.split(",")]
            for renglon in renglones:
                if renglon not in acumulados_renglones:
                    acumulados_renglones[renglon] = {"valor_total": 0.0, "cantidad": 0}
                acumulados_renglones[renglon]["valor_total"] += reg.valor
                acumulados_renglones[renglon]["cantidad"] += 1

    renglones_sugeridos = [
        RenglonSugerido(renglon=renglon, valor_total=datos["valor_total"], cantidad_registros=datos["cantidad"])
        for renglon, datos in acumulados_renglones.items()
    ]

    return BorradorRenglones(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        renglones=renglones_sugeridos
    )