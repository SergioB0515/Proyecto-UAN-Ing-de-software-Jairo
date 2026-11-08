import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from ..contribuyentes.servicios import (
    listar_activos,
    listar_fuentes_ingreso,
    obtener_periodo_fiscal,
)
from ..exogena.modelos import RegistroExogena, TopeExogena
from ..exogena.servicios import obtener_reporte_mas_reciente
from ..liquidacion.formulario_210 import casilla_por_numero
from .modelos import (
    BorradorRenglones,
    EstadoConciliacion,
    ItemConciliacion,
    OrigenItemConciliacion,
    CuadreTope,
    RegistroSinAsignar,
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
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    anio_gravable = periodo.anio_gravable
    reporte = obtener_reporte_mas_reciente(session, periodo_fiscal_id)

    registros = session.exec(
        select(RegistroExogena).where(RegistroExogena.reporte_exogena_id == reporte.id)
    ).all()

    acumulados: Dict[str, RenglonSugerido] = {}
    sin_asignar: List[RegistroSinAsignar] = []

    for registro in registros:
        if not registro.renglones_sugeridos:
            continue
        renglones = sorted(
            {r.strip() for r in registro.renglones_sugeridos.split(",") if r.strip()},
            key=_numero_renglon,
        )

        # Cuando la DIAN ofrece varios renglones posibles en vez de asignar
        # uno ("según el bien o derecho reportado se puede usar en renglones
        # como..."), sumar el valor en todos cuenta la misma plata varias
        # veces: como patrimonio, como deuda y como ganancia ocasional a la
        # vez. Se aparta para que lo asigne el contador.
        if registro.renglones_son_condicionales:
            sin_asignar.append(
                RegistroSinAsignar(
                    detalle=registro.detalle,
                    valor=registro.valor,
                    renglones_posibles=renglones,
                    uso_sugerido=registro.uso_sugerido,
                )
            )
            continue

        for renglon in renglones:
            acumulado = acumulados.setdefault(
                renglon,
                RenglonSugerido(renglon=renglon, valor_total=0.0, cantidad_registros=0),
            )
            acumulado.valor_total += registro.valor
            acumulado.cantidad_registros += 1

    # Nombre oficial de la casilla, del catálogo del formulario 210.
    for acumulado in acumulados.values():
        casilla = casilla_por_numero(_numero_renglon(acumulado.renglon), anio_gravable)
        if casilla is not None:
            acumulado.casilla = casilla.numero
            acumulado.nombre_oficial = casilla.nombre

    cuadres, diagnosticos = _cuadrar_contra_topes(session, reporte.id, acumulados)
    if sin_asignar:
        total = sum(r.valor for r in sin_asignar)
        diagnosticos.insert(
            0,
            f"{len(sin_asignar)} registro(s) por ${total:,.0f} traen varios renglones "
            f"posibles en vez de uno asignado. NO se sumaron a ningún renglón: "
            f"asígnelos usted, porque repartirlos en todos contaría el mismo valor "
            f"varias veces.",
        )

    return BorradorRenglones(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        reporte_exogena_id=reporte.id,
        renglones=sorted(acumulados.values(), key=lambda r: _numero_renglon(r.renglon)),
        sin_asignar=sin_asignar,
        cuadres=cuadres,
        diagnosticos=diagnosticos,
    )


# Renglones del borrador que deben cuadrar contra un tope del mismo archivo.
# El archivo de la DIAN trae las dos cosas, así que se puede verificar solo.
_CUADRES = {"Tope 2 - Patrimonio": "R29"}


def _cuadrar_contra_topes(
    session: Session, reporte_id: int, acumulados: Dict[str, RenglonSugerido]
) -> Tuple[List[CuadreTope], List[str]]:
    """Contrasta el borrador contra los topes que viene en el propio archivo.

    Es una verificación gratis: la DIAN informa el detalle y también el tope
    consolidado, así que si el renglón armado con el detalle no coincide con
    el tope, algo se contó de más o de menos. Antes nadie lo miraba.
    """
    cuadres: List[CuadreTope] = []
    diagnosticos: List[str] = []
    topes = session.exec(
        select(TopeExogena).where(TopeExogena.reporte_exogena_id == reporte_id)
    ).all()

    for tope in topes:
        renglon = _CUADRES.get(tope.etiqueta.strip())
        if renglon is None:
            continue
        acumulado = acumulados.get(renglon)
        valor = acumulado.valor_total if acumulado else 0.0
        diferencia = round(valor - tope.valor, 2)
        cuadra = abs(diferencia) < 1
        cuadres.append(
            CuadreTope(
                etiqueta=tope.etiqueta,
                valor_tope=tope.valor,
                valor_borrador=valor,
                diferencia=diferencia,
                cuadra=cuadra,
            )
        )
        if not cuadra:
            sentido = "más" if diferencia > 0 else "menos"
            diagnosticos.append(
                f"El renglón {renglon} suma ${valor:,.0f} y el «{tope.etiqueta}» que "
                f"reporta el mismo archivo es ${tope.valor:,.0f}: "
                f"${abs(diferencia):,.0f} de {sentido}. Revise si algún registro se "
                f"contó dos veces o si falta alguno."
            )
    return cuadres, diagnosticos
