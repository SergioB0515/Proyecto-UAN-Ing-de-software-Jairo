from core.formato import pesos
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
from decimal import Decimal

from core.excepciones import UmbralNoConfiguradoError

from ..liquidacion.formulario_210 import casilla_por_numero
from . import cruce
from .modelos import (
    ComparacionCruce,
    CruceDian,
    DetalleTopeLeer,
    RegistroPendiente,
    TopeCruzado,
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
        # Consumos con tarjeta, compras y movimientos de cuentas son flujos, no
        # bienes ni ingresos: no se «declaran» como un activo o una fuente de
        # ingreso, así que marcarlos como no declarados sería una alarma falsa.
        # Se analizan en el cruce con la DIAN, frente a los ingresos. Las
        # inversiones (un CDT) sí se quedan: dejan un activo o un rendimiento.
        if _a_cruce(registro).es_flujo_sin_bien:
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
            # Un bien en copropiedad cuenta por el porcentaje de participación
            # que trae el archivo, no completo.
            acumulado.valor_total += float(_a_cruce(registro).valor_propio)
            acumulado.cantidad_registros += 1

    # Nombre oficial de la casilla, del catálogo del formulario 210.
    for acumulado in acumulados.values():
        casilla = casilla_por_numero(_numero_renglon(acumulado.renglon), anio_gravable)
        if casilla is not None:
            acumulado.casilla = casilla.numero
            acumulado.nombre_oficial = casilla.nombre

    cuadres, diagnosticos = _cuadrar_contra_topes(session, reporte.id, registros, acumulados)
    if sin_asignar:
        total = sum(r.valor for r in sin_asignar)
        diagnosticos.insert(
            0,
            f"{len(sin_asignar)} registro(s) por {pesos(total)} traen varios renglones "
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


def _a_cruce(registro: RegistroExogena) -> cruce.Registro:
    return cruce.Registro(
        detalle=registro.detalle or "",
        valor=Decimal(str(registro.valor)),
        uso_sugerido=registro.uso_sugerido or "",
        info_adicional=registro.info_adicional or "",
        renglones_sugeridos=registro.renglones_sugeridos or "",
        renglones_son_condicionales=registro.renglones_son_condicionales,
        es_auto_reportado=registro.es_auto_reportado,
        es_dian=registro.es_dian,
        nombre_reportante=registro.nombre_reportante or "",
    )


def _topes_del_reporte(session: Session, reporte_id: int) -> Dict[str, Decimal]:
    topes = session.exec(
        select(TopeExogena).where(TopeExogena.reporte_exogena_id == reporte_id)
    ).all()
    return {t.etiqueta.strip(): Decimal(str(t.valor)) for t in topes}


def _cuadrar_contra_topes(
    session: Session,
    reporte_id: int,
    registros: List[RegistroExogena],
    acumulados: Dict[str, RenglonSugerido],
) -> Tuple[List[CuadreTope], List[str]]:
    """Reconstruye los cinco topes desde el detalle del propio archivo.

    Es una verificación gratis: la DIAN informa el detalle y también el tope
    consolidado, así que si el detalle no reproduce el tope, algo se leyó mal.

    El tope de patrimonio NO es la suma del renglón 29: es el mayor entre lo
    reportado por terceros y el patrimonio declarado el año anterior. Una
    versión anterior los comparaba directamente y daba una falsa alarma cada
    vez que el contribuyente había declarado el año pasado más de lo que los
    terceros reportan este.
    """
    cuadres: List[CuadreTope] = []
    diagnosticos: List[str] = []
    for c in cruce.cuadrar_topes(
        [_a_cruce(r) for r in registros], _topes_del_reporte(session, reporte_id)
    ):
        cuadres.append(
            CuadreTope(
                etiqueta=c.etiqueta,
                valor_tope=float(c.valor_tope),
                valor_borrador=float(c.valor_esperado),
                diferencia=float(c.valor_esperado - c.valor_tope),
                cuadra=c.cuadra,
            )
        )
        if not c.cuadra:
            diagnosticos.append(f"{c.etiqueta}: {c.explicacion}")
        if c.numero == 2 and c.piso is not None and c.piso > c.suma_detalle:
            sugerido = acumulados.get("R29")
            valor = sugerido.valor_total if sugerido else 0.0
            diagnosticos.append(
                f"El patrimonio bruto declarado el año anterior ({pesos(c.piso)}) es "
                f"mayor que lo que los terceros reportan este año ({pesos(valor)} "
                f"sugeridos para el renglón 29). La exógena no trae todo el "
                f"patrimonio: si no hubo ventas, el renglón 29 real es más alto que "
                f"el sugerido."
            )
    return cuadres, diagnosticos


def cruzar_con_la_dian(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> CruceDian:
    """Compara el borrador de liquidación con lo que la DIAN ya sabe."""
    # Import tardío: la liquidación depende de medio sistema y este módulo se
    # carga antes en el arranque.
    from ..liquidacion import servicios as liquidacion
    from ..parametros.servicios import obtener_umbral_vigente

    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    reporte = obtener_reporte_mas_reciente(session, periodo_fiscal_id)
    registros = session.exec(
        select(RegistroExogena)
        .where(RegistroExogena.reporte_exogena_id == reporte.id)
        .order_by(RegistroExogena.id)
    ).all()

    umbrales: Optional[Dict[int, Decimal]] = None
    try:
        u = obtener_umbral_vigente(session, periodo.anio_gravable)
        uvt = Decimal(str(u.valor_uvt))
        umbrales = {
            1: uvt * Decimal(str(u.tope_ingresos_uvt)),
            2: uvt * Decimal(str(u.tope_patrimonio_uvt)),
            3: uvt * Decimal(str(u.tope_consumo_tc_uvt)),
            4: uvt * Decimal(str(u.tope_movimiento_uvt)),
            5: uvt * Decimal(str(u.tope_compras_uvt)),
        }
    except UmbralNoConfiguradoError:
        pass

    liq = liquidacion.liquidar_periodo(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    hoja = liquidacion.obtener_hoja(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    parametros = liquidacion.obtener_parametros(periodo.anio_gravable)
    declarado = cruce.CifrasDeclaradas(
        casillas={r.casilla: Decimal(r.valor) for r in liq.renglones if r.casilla},
        compras_con_factura_electronica=Decimal(
            str(hoja.compras_con_factura_electronica or 0)
        ),
        uvt=parametros.uvt,
        tope_compras_uvt=parametros.deduccion_compras.tope_uvt or Decimal("240"),
    )

    resultado = cruce.cruzar(
        [_a_cruce(r) for r in registros],
        _topes_del_reporte(session, reporte.id),
        declarado,
        umbrales,
    )

    def pendiente(r: cruce.Registro) -> RegistroPendiente:
        return RegistroPendiente(
            detalle=r.detalle,
            valor=r.valor,
            renglones_posibles=[f"R{n}" for n in r.renglones()],
            uso_sugerido=r.uso_sugerido or None,
        )

    severidades = (cruce.ALTA, cruce.MEDIA, cruce.OPORTUNIDAD, cruce.OK, cruce.SIN_DATO)
    return CruceDian(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        anio_gravable=periodo.anio_gravable,
        reporte_exogena_id=reporte.id,
        obligado_a_declarar=(
            any(t.supera_umbral for t in resultado.topes) if umbrales else None
        ),
        topes=[
            TopeCruzado(
                numero=t.numero, nombre=t.nombre, etiqueta=t.etiqueta,
                valor_tope=t.valor_tope, suma_detalle=t.suma_detalle, piso=t.piso,
                valor_esperado=t.valor_esperado, cuadra=t.cuadra, umbral=t.umbral,
                supera_umbral=t.supera_umbral, explicacion=t.explicacion,
                registros=[
                    DetalleTopeLeer(
                        detalle=d.detalle, reportante=d.reportante, valor=d.valor,
                        valor_propio=d.valor_propio, participacion=d.participacion,
                    )
                    for d in t.registros
                ],
            )
            for t in resultado.topes
        ],
        comparaciones=[
            ComparacionCruce(
                clave=c.clave, titulo=c.titulo, casillas=c.casillas,
                valor_dian=c.valor_dian, valor_declarado=c.valor_declarado,
                diferencia=c.diferencia, severidad=c.severidad, mensaje=c.mensaje,
            )
            for c in resultado.comparaciones
        ],
        pendientes=[pendiente(r) for r in resultado.pendientes],
        informativos=[pendiente(r) for r in resultado.informativos],
        resumen={s: resultado.cuenta(s) for s in severidades},
        diagnosticos=resultado.diagnosticos,
    )
