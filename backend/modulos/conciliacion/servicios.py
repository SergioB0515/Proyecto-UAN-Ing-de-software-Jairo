import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlmodel import Session, select

from ..contribuyentes.servicios import (
    listar_activos,
    listar_fuentes_ingreso,
    obtener_periodo_fiscal,
)
from ..exogena.modelos import RegistroExogena
from ..exogena.servicios import obtener_reporte_mas_reciente
from .modelos import (
    BorradorRenglones,
    EstadoConciliacion,
    ItemConciliacion,
    OrigenItemConciliacion,
    RenglonSugerido,
    ResultadoConciliacion,
)

CONCEPTO_CONSUMO_TC = "1023"

TOLERANCIA_ABSOLUTA = 1000.0
TOLERANCIA_RELATIVA = 0.005


@dataclass
class _ItemDeclarado:
    concepto: str
    valor: float
    origen: OrigenItemConciliacion
    vinculo_codigo_concepto: Optional[str]
    vinculo_palabra_clave: Optional[str]


def _es_retencion(registro: RegistroExogena) -> bool:
    return "retenci" in (registro.detalle or "").lower()


def _excluido_del_cruce(registro: RegistroExogena) -> bool:
    return registro.es_auto_reportado or registro.es_dian or _es_retencion(registro)


def _dentro_de_tolerancia(valor_exogena: float, valor_declarado: float) -> bool:
    tolerancia = max(TOLERANCIA_ABSOLUTA, abs(valor_exogena) * TOLERANCIA_RELATIVA)
    return abs(valor_exogena - valor_declarado) <= tolerancia


def _buscar_registro(
    item: _ItemDeclarado, candidatos: List[RegistroExogena], usados: set
) -> Optional[RegistroExogena]:
    disponibles = [r for r in candidatos if r.id not in usados]

    coincidencias: List[RegistroExogena] = []
    if item.vinculo_codigo_concepto:
        codigo = item.vinculo_codigo_concepto.strip()
        coincidencias = [r for r in disponibles if r.concepto_code == codigo]
    if not coincidencias and item.vinculo_palabra_clave:
        palabra = item.vinculo_palabra_clave.strip().lower()
        coincidencias = [r for r in disponibles if palabra in (r.detalle or "").lower()]

    if not coincidencias:
        return None
    return min(coincidencias, key=lambda r: abs(r.valor - item.valor))


def conciliar_contribuyente(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> ResultadoConciliacion:
    obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    reporte = obtener_reporte_mas_reciente(session, periodo_fiscal_id)

    registros = session.exec(
        select(RegistroExogena)
        .where(RegistroExogena.reporte_exogena_id == reporte.id)
        .order_by(RegistroExogena.id)
    ).all()
    candidatos = [r for r in registros if not _excluido_del_cruce(r)]

    declarados = [
        _ItemDeclarado(
            concepto=activo.descripcion,
            valor=activo.valor,
            origen=OrigenItemConciliacion.ACTIVO,
            vinculo_codigo_concepto=activo.vinculo_codigo_concepto,
            vinculo_palabra_clave=activo.vinculo_palabra_clave,
        )
        for activo in listar_activos(
            session, contador_id, contribuyente_id, periodo_fiscal_id
        )
    ] + [
        _ItemDeclarado(
            concepto=fuente.concepto,
            valor=fuente.valor_anual,
            origen=OrigenItemConciliacion.FUENTE_INGRESO,
            vinculo_codigo_concepto=fuente.vinculo_codigo_concepto,
            vinculo_palabra_clave=fuente.vinculo_palabra_clave,
        )
        for fuente in listar_fuentes_ingreso(
            session, contador_id, contribuyente_id, periodo_fiscal_id
        )
    ]

    items: List[ItemConciliacion] = []
    usados: set = set()

    for declarado in declarados:
        registro = _buscar_registro(declarado, candidatos, usados)
        if registro is None:
            items.append(
                ItemConciliacion(
                    concepto=declarado.concepto,
                    origen=declarado.origen,
                    valor_declarado=declarado.valor,
                    estado=EstadoConciliacion.NO_REPORTADO_POR_TERCERO,
                )
            )
            continue

        usados.add(registro.id)
        items.append(
            ItemConciliacion(
                concepto=declarado.concepto,
                origen=declarado.origen,
                valor_declarado=declarado.valor,
                valor_exogena=registro.valor,
                diferencia=registro.valor - declarado.valor,
                estado=(
                    EstadoConciliacion.COINCIDE
                    if _dentro_de_tolerancia(registro.valor, declarado.valor)
                    else EstadoConciliacion.DISCREPANCIA
                ),
                registro_exogena_id=registro.id,
                nit_reportante=registro.nit_reportante,
                nombre_reportante=registro.nombre_reportante,
                concepto_code=registro.concepto_code,
            )
        )

    for registro in candidatos:
        if registro.id in usados or registro.concepto_code == CONCEPTO_CONSUMO_TC:
            continue
        items.append(
            ItemConciliacion(
                concepto=registro.detalle,
                origen=OrigenItemConciliacion.EXOGENA,
                valor_exogena=registro.valor,
                estado=EstadoConciliacion.NO_DECLARADO,
                registro_exogena_id=registro.id,
                nit_reportante=registro.nit_reportante,
                nombre_reportante=registro.nombre_reportante,
                concepto_code=registro.concepto_code,
            )
        )

    resumen: Dict[EstadoConciliacion, int] = {estado: 0 for estado in EstadoConciliacion}
    for item in items:
        resumen[item.estado] += 1

    return ResultadoConciliacion(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        reporte_exogena_id=reporte.id,
        items=items,
        resumen=resumen,
    )


def _numero_renglon(renglon: str) -> int:
    digitos = re.sub(r"\D", "", renglon)
    return int(digitos) if digitos else 0


def generar_borrador_renglones(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> BorradorRenglones:
    obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    reporte = obtener_reporte_mas_reciente(session, periodo_fiscal_id)

    registros = session.exec(
        select(RegistroExogena).where(RegistroExogena.reporte_exogena_id == reporte.id)
    ).all()

    acumulados: Dict[str, RenglonSugerido] = {}
    for registro in registros:
        if not registro.renglones_sugeridos:
            continue
        renglones = {r.strip() for r in registro.renglones_sugeridos.split(",") if r.strip()}
        for renglon in renglones:
            acumulado = acumulados.setdefault(
                renglon,
                RenglonSugerido(renglon=renglon, valor_total=0.0, cantidad_registros=0),
            )
            acumulado.valor_total += registro.valor
            acumulado.cantidad_registros += 1

    return BorradorRenglones(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        reporte_exogena_id=reporte.id,
        renglones=sorted(acumulados.values(), key=lambda r: _numero_renglon(r.renglon)),
    )
