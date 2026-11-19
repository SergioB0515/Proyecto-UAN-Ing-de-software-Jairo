from core.formato import pesos
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from core.excepciones import DecisionRenglonInvalidaError

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
from ..portal.modelos import DatoAdicional, TipoAdicional
from . import cruce
from .modelos import (
    ComparacionCruce,
    CruceDian,
    DetalleTopeLeer,
    RegistroPendiente,
    TopeCruzado,
    BorradorRenglones,
    DecisionRenglon,
    DecisionRenglonFijar,
    DecisionRenglonLeer,
    ETIQUETAS_ESTADO,
    EstadoConciliacion,
    FuenteValorFinal,
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
    clave: str
    concepto: str
    valor: float
    origen: OrigenItemConciliacion
    vinculo_codigo_concepto: Optional[str]
    vinculo_palabra_clave: Optional[str]


# Adicionales que SÍ se intentan cruzar con la exógena: un apartamento, un
# carro o una deuda bancaria pueden estar reportados por un tercero, así que
# vale la pena buscarlos.
_ADICIONALES_PATRIMONIALES = {
    TipoAdicional.ACTIVO,
    TipoAdicional.DEUDA,
    TipoAdicional.BIEN_EXTERIOR,
}

# Adicionales que por definición NO están en la exógena: ningún tercero le
# reporta a la DIAN lo que alguien pagó de medicina prepagada. Entran a la
# tabla, pero buscarles pareja sería buscar lo que no existe, y un cruce por
# palabra clave solo produciría falsos positivos.
_ADICIONALES_SIN_CRUCE = {
    TipoAdicional.INTERESES_VIVIENDA,
    TipoAdicional.MEDICINA_PREPAGADA,
    TipoAdicional.AHORRO_AFC,
    TipoAdicional.APORTES_VOLUNTARIOS_PENSION,
}

# Los dependientes se quedan fuera de esta tabla: son un número de personas,
# no un valor en pesos, y meter un conteo en una columna de dinero es una
# cifra que después alguien suma. Se ven en la pestaña de Adicionales y en la
# lista de documentos que se le piden, que es donde significan algo.


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


def _ventas_declaradas(session: Session, periodo_fiscal_id: int) -> List[_ItemDeclarado]:
    """Ventas de inmuebles registradas, para cruzar con el reporte de la notaría.

    El concepto 1032 incluye vendedor y comprador: se exige además que el detalle
    mencione venta o enajenante.
    """
    from ..liquidacion.modelos import VentaInmueble

    return [
        _ItemDeclarado(
            clave=f"VTA:{v.id}",
            concepto=f"Venta: {v.descripcion}",
            valor=float(v.valor_venta),
            origen=OrigenItemConciliacion.VENTA_INMUEBLE,
            vinculo_codigo_concepto=None,
            vinculo_palabra_clave="enajenante principal",
        )
        for v in session.exec(select(VentaInmueble).where(
            VentaInmueble.periodo_fiscal_id == periodo_fiscal_id)).all()
    ]


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
            clave=f"ACT:{activo.id}",
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
            clave=f"ING:{fuente.id}",
            concepto=fuente.concepto,
            valor=fuente.valor_anual,
            origen=OrigenItemConciliacion.FUENTE_INGRESO,
            vinculo_codigo_concepto=fuente.vinculo_codigo_concepto,
            vinculo_palabra_clave=fuente.vinculo_palabra_clave,
        )
        for fuente in listar_fuentes_ingreso(
            session, contador_id, contribuyente_id, periodo_fiscal_id
        )
    ] + _ventas_declaradas(session, periodo_fiscal_id) + _adicionales_declarados(
        session, periodo_fiscal_id
    )

    items: List[ItemConciliacion] = []
    usados: set = set()

    for declarado in declarados:
        registro = _buscar_registro(declarado, candidatos, usados)
        if registro is None:
            items.append(
                ItemConciliacion(
                    clave=declarado.clave,
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
                clave=declarado.clave,
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
        # Tarjeta, compras y movimientos son flujos: no se marcan como no declarados.
        # Se analizan en el cruce frente a ingresos. Las inversiones sí se buscan.
        if _a_cruce(registro).es_flujo_sin_bien:
            continue
        items.append(
            ItemConciliacion(
                clave=f"EXO:{registro.id}",
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
        item.etiqueta_estado = ETIQUETAS_ESTADO[item.estado]

    decididos = _aplicar_decisiones(session, periodo_fiscal_id, items)

    return ResultadoConciliacion(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        reporte_exogena_id=reporte.id,
        items=items,
        resumen=resumen,
        total_decididos=decididos,
        total_sin_decidir=len(items) - decididos,
    )


def _adicionales_declarados(
    session: Session, periodo_fiscal_id: int
) -> List[_ItemDeclarado]:
    """Los adicionales, como una fila declarada más de la misma tabla."""
    adicionales = session.exec(
        select(DatoAdicional)
        .where(DatoAdicional.periodo_fiscal_id == periodo_fiscal_id)
        .order_by(DatoAdicional.id)
    ).all()

    salida: List[_ItemDeclarado] = []
    for adicional in adicionales:
        if adicional.tipo not in _ADICIONALES_PATRIMONIALES | _ADICIONALES_SIN_CRUCE:
            continue
        cruzable = adicional.tipo in _ADICIONALES_PATRIMONIALES
        salida.append(
            _ItemDeclarado(
                clave=f"ADI:{adicional.id}",
                concepto=f"{adicional.descripcion} ({_nombre_adicional(adicional.tipo)})",
                valor=float(adicional.valor),
                origen=OrigenItemConciliacion.ADICIONAL,
                vinculo_codigo_concepto=None,
                # La descripción hace de palabra clave, igual que en un activo
                # registrado por el contador: si el tercero reportó «Apartamento
                # calle 50», el cruce lo encuentra.
                vinculo_palabra_clave=adicional.descripcion if cruzable else None,
            )
        )
    return salida


_NOMBRES_ADICIONAL = {
    TipoAdicional.ACTIVO: "activo",
    TipoAdicional.DEUDA: "deuda",
    TipoAdicional.BIEN_EXTERIOR: "bien en el exterior",
    TipoAdicional.INTERESES_VIVIENDA: "intereses de vivienda",
    TipoAdicional.MEDICINA_PREPAGADA: "medicina prepagada",
    TipoAdicional.AHORRO_AFC: "ahorro AFC/AVC",
    TipoAdicional.APORTES_VOLUNTARIOS_PENSION: "aportes voluntarios a pensión",
}


def _nombre_adicional(tipo: TipoAdicional) -> str:
    return _NOMBRES_ADICIONAL.get(tipo, tipo.value.lower())


def _aplicar_decisiones(
    session: Session, periodo_fiscal_id: int, items: List[ItemConciliacion]
) -> int:
    decisiones = {
        d.clave_item: d
        for d in session.exec(
            select(DecisionRenglon).where(
                DecisionRenglon.periodo_fiscal_id == periodo_fiscal_id
            )
        ).all()
    }
    aplicadas = 0
    for item in items:
        decision = decisiones.get(item.clave)
        if decision is None:
            continue
        item.valor_final = float(decision.valor_final)
        item.fuente_valor_final = decision.fuente_elegida
        item.nota_decision = decision.nota
        item.decidida_en = decision.decidida_en
        aplicadas += 1
    return aplicadas


def _valor_de_la_fuente(
    item: ItemConciliacion, datos: DecisionRenglonFijar
) -> Decimal:
    """El valor final según la fuente elegida, no según lo que mande el cliente.

    Con EXOGENA o DECLARADO el número lo pone la fila: aceptar el que venga en
    el cuerpo permitiría guardar «elegí el valor de la exógena» junto a una
    cifra distinta, y el registro de la decisión dejaría de ser cierto.
    """
    if datos.fuente_elegida == FuenteValorFinal.EXOGENA:
        if item.valor_exogena is None:
            raise DecisionRenglonInvalidaError(
                f"«{item.concepto}» no tiene valor en la exógena: no se puede "
                "elegir esa fuente. Use DECLARADO o MANUAL."
            )
        return Decimal(str(item.valor_exogena)).quantize(Decimal("0.01"))

    if datos.fuente_elegida == FuenteValorFinal.DECLARADO:
        if item.valor_declarado is None:
            raise DecisionRenglonInvalidaError(
                f"«{item.concepto}» solo está en la exógena: no hay valor "
                "declarado que elegir. Use EXOGENA o MANUAL."
            )
        return Decimal(str(item.valor_declarado)).quantize(Decimal("0.01"))

    if datos.valor_final is None:
        raise DecisionRenglonInvalidaError(
            "Con fuente MANUAL hay que enviar el valor final"
        )
    return Decimal(datos.valor_final).quantize(Decimal("0.01"))


def fijar_decision(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: DecisionRenglonFijar,
) -> DecisionRenglonLeer:
    """Fija el valor final de un renglón. Solo lo hace el contador.

    No existe una ruta equivalente en el portal del contribuyente: él informa
    y aporta soportes, y quien decide qué se declara —y firma— es el contador.
    """
    conciliacion = conciliar_contribuyente(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    item = next((i for i in conciliacion.items if i.clave == datos.clave_item), None)
    if item is None:
        raise DecisionRenglonInvalidaError(
            f"La conciliación de este periodo no tiene un renglón "
            f"«{datos.clave_item}». Vuelva a cargarla: pudo cambiar con una "
            "versión nueva de la exógena."
        )

    valor = _valor_de_la_fuente(item, datos)

    decision = session.exec(
        select(DecisionRenglon).where(
            DecisionRenglon.periodo_fiscal_id == periodo_fiscal_id,
            DecisionRenglon.clave_item == datos.clave_item,
        )
    ).first()
    if decision is None:
        decision = DecisionRenglon(
            contribuyente_id=contribuyente_id,
            periodo_fiscal_id=periodo_fiscal_id,
            clave_item=datos.clave_item,
            valor_final=valor,
            fuente_elegida=datos.fuente_elegida,
        )
    decision.valor_final = valor
    decision.fuente_elegida = datos.fuente_elegida
    decision.nota = (datos.nota or "").strip() or None
    decision.decidida_por_contador_id = contador_id
    decision.decidida_en = datetime.now(timezone.utc)
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return DecisionRenglonLeer(**decision.model_dump())


def listar_decisiones(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[DecisionRenglonLeer]:
    obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    decisiones = session.exec(
        select(DecisionRenglon)
        .where(DecisionRenglon.periodo_fiscal_id == periodo_fiscal_id)
        .order_by(DecisionRenglon.clave_item)
    ).all()
    return [DecisionRenglonLeer(**d.model_dump()) for d in decisiones]


def borrar_decision(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    clave_item: str,
) -> None:
    obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    decision = session.exec(
        select(DecisionRenglon).where(
            DecisionRenglon.periodo_fiscal_id == periodo_fiscal_id,
            DecisionRenglon.clave_item == clave_item,
        )
    ).first()
    if decision is None:
        raise DecisionRenglonInvalidaError(
            f"No hay una decisión guardada para «{clave_item}»"
        )
    session.delete(decision)
    session.commit()


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

        # Varios renglones posibles: se aparta para que lo asigne el contador,
        # en vez de contarlo en todos.
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
            # Copropiedad: cuenta por el porcentaje de participación.
            acumulado.valor_total += float(_a_cruce(registro).valor_propio)
            acumulado.cantidad_registros += 1

    # Nombre oficial de la casilla.
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
    """Reconstruye los cinco topes desde el detalle del archivo.

    Tope de patrimonio = max(terceros, patrimonio declarado el año anterior).
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
    """Cruza la liquidación con la exógena."""
    # Import tardío: liquidacion se carga después en el arranque.
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
