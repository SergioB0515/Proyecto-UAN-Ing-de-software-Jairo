"""Servicios de gestión: etapas, documentos, presentación, firmeza,
corrección, intereses y tasas.
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from core.excepciones import ErrorAplicacion
from core.formato import pesos
from ..contribuyentes.modelos import EstadoPeriodo, PeriodoFiscal
from ..contribuyentes.servicios import obtener_contribuyente, obtener_periodo_fiscal
from ..adjuntos.modelos import Adjunto, TipoEntidadAdjunto
from ..exogena.modelos import RegistroExogena, ReporteExogena
from ..liquidacion import servicios as liquidacion
from ..liquidacion.borrador_210 import construir_casillas
from ..liquidacion.formulario_210 import CASILLAS_2024
from ..liquidacion.modelos import DeduccionSolicitada, HojaLiquidacion
from ..parametros.tablas_oficiales import PARAMETROS_POR_ANIO
from ..portal.modelos import DatoAdicional, TipoAdicional
from . import calculos
from .modelos import (
    ArchivoDocumento,
    BeneficioLeer,
    CoherenciaLeer,
    ComparativoLeer,
    CondicionLeer,
    CorreccionLeer,
    DeclaracionAnteriorRegistrar,
    DeclaracionPresentada,
    DeclaracionPresentadaLeer,
    DocumentoActualizar,
    DocumentoCrear,
    DocumentoLeer,
    DocumentoSolicitado,
    EstadoDocumento,
    EtapaLeer,
    FilaComparativoLeer,
    FirmezaLeer,
    GestionLeer,
    InteresesLeer,
    PresentacionRegistrar,
    ProcesoLeer,
    SeguimientoActualizar,
    SeguimientoDeclaracion,
    SolicitudDocumentosLeer,
    TasaInteresDatos,
    TasaInteresMoratorio,
    TramoInteresLeer,
)

CERO = Decimal("0")
CIEN = Decimal("100")


class DocumentoNoEncontradoError(ErrorAplicacion):
    pass


class DatosInvalidosError(ErrorAplicacion):
    pass


# Lecturas


def _hoy() -> date:
    from ..parametros.servicios import hoy_colombia

    return hoy_colombia()


def _vencimiento(session: Session, rut: str, periodo: PeriodoFiscal) -> Optional[date]:
    from ..parametros.servicios import calcular_vencimiento

    return calcular_vencimiento(
        session, rut, periodo.anio_gravable,
        periodo.fecha_vencimiento_manual, periodo.fecha_presentacion,
    ).fecha


def _seguimiento(session: Session, periodo_id: int) -> SeguimientoDeclaracion:
    s = session.get(SeguimientoDeclaracion, periodo_id)
    return s if s is not None else SeguimientoDeclaracion(periodo_fiscal_id=periodo_id)


def _casillas_de(declaracion: DeclaracionPresentada) -> Dict[int, Decimal]:
    return {int(k): Decimal(v) for k, v in (declaracion.casillas or {}).items()}


def _presentaciones(session: Session, periodo_id: int) -> List[DeclaracionPresentada]:
    return list(session.exec(
        select(DeclaracionPresentada)
        .where(DeclaracionPresentada.periodo_fiscal_id == periodo_id)
        .order_by(DeclaracionPresentada.fecha_presentacion, DeclaracionPresentada.id)
    ).all())


def _leer_presentada(d: DeclaracionPresentada, anio: int) -> DeclaracionPresentadaLeer:
    return DeclaracionPresentadaLeer(
        id=d.id, anio_gravable=anio, fecha_presentacion=d.fecha_presentacion,
        numero_formulario=d.numero_formulario, es_correccion=d.es_correccion,
        origen=d.origen, casillas=_casillas_de(d),
    )


def declaracion_vigente(
    session: Session, contribuyente_id: int, anio_gravable: int
) -> Optional[DeclaracionPresentada]:
    """Última declaración presentada de un año (la corrección prevalece)."""
    periodo = session.exec(select(PeriodoFiscal).where(
        PeriodoFiscal.contribuyente_id == contribuyente_id,
        PeriodoFiscal.anio_gravable == anio_gravable,
    )).first()
    if periodo is None:
        return None
    presentadas = _presentaciones(session, periodo.id)
    return presentadas[-1] if presentadas else None


def _tasas(session: Session) -> Dict[Tuple[int, int], Decimal]:
    """Tasas por mes, en fracción: oficiales con las de la base encima."""
    return {(t.anio, t.mes): Decimal(t.tasa_efectiva_anual) / CIEN
            for t in listar_tasas(session)}


def _uvt(anio: int, respaldo: Decimal) -> Decimal:
    parametros = PARAMETROS_POR_ANIO.get(anio)
    return parametros.uvt if parametros else respaldo


# Documentos


def _documentos(
    session: Session, contribuyente_id: int, periodo: PeriodoFiscal
) -> List[DocumentoLeer]:
    reportes = session.exec(select(ReporteExogena.id).where(
        ReporteExogena.periodo_fiscal_id == periodo.id)).all()
    registros = session.exec(select(RegistroExogena).where(
        RegistroExogena.reporte_exogena_id.in_(reportes))).all() if reportes else []
    hoja = session.get(HojaLiquidacion, periodo.id)
    deducciones = session.exec(select(DeduccionSolicitada).where(
        DeduccionSolicitada.periodo_fiscal_id == periodo.id)).all()

    # Lo que el contribuyente registró por el portal cuenta como fuente de
    # documentos igual que una deducción que el contador haya solicitado: si
    # dice que paga medicina prepagada, hay que pedirle el certificado. Así la
    # lista de documentos es una sola, venga el dato de donde venga.
    adicionales = session.exec(select(DatoAdicional).where(
        DatoAdicional.periodo_fiscal_id == periodo.id)).all()
    codigos = [d.codigo_plantilla for d in deducciones if d.codigo_plantilla]
    codigos += [
        a.tipo.value for a in adicionales
        if a.tipo.value in calculos.codigos_con_documento()
    ]
    dependientes_portal = sum(
        (a.cantidad or 0) for a in adicionales if a.tipo == TipoAdicional.DEPENDIENTE
    )
    deudas_portal = any(a.tipo == TipoAdicional.DEUDA for a in adicionales)

    sugeridos = calculos.sugerir_documentos(
        [calculos.RegistroParaDocumentos(
            r.nit_reportante, r.nombre_reportante, r.detalle, r.concepto_code,
            r.info_adicional, r.es_auto_reportado, r.es_dian) for r in registros],
        codigos,
        numero_dependientes=max(hoja.numero_dependientes if hoja else 0,
                                dependientes_portal),
        tiene_declaracion_anterior=declaracion_vigente(
            session, contribuyente_id, periodo.anio_gravable - 1) is not None,
        tiene_deudas=bool(hoja and hoja.deudas and hoja.deudas > 0) or deudas_portal,
    )
    guardados = {d.clave: d for d in session.exec(select(DocumentoSolicitado).where(
        DocumentoSolicitado.periodo_fiscal_id == periodo.id)).all()}
    archivos = _archivos_por_documento(
        session, [g.id for g in guardados.values() if g.id]
    )

    def leer(clave, descripcion, tercero, nit, motivo, reconocido, g) -> DocumentoLeer:
        propios = archivos.get(g.id, []) if g else []
        estado = g.estado if g else EstadoDocumento.PENDIENTE
        return DocumentoLeer(
            id=g.id if g else None, clave=clave, descripcion=descripcion,
            tercero=tercero, nit=nit, motivo=motivo, estado=estado,
            actualizado_en=g.actualizado_en if g else None,
            manual=g.manual if g else False,
            nota=g.nota if g else "",
            valor_informado=g.valor_informado if g else None,
            respondido_por_contribuyente=(
                g.respondido_por_contribuyente if g else False
            ),
            reconocido=reconocido,
            archivos=propios,
            resuelto=estado not in (
                EstadoDocumento.PENDIENTE, EstadoDocumento.NO_ENTIENDO
            ),
        )

    salida: List[DocumentoLeer] = []
    for s in sugeridos:
        salida.append(leer(s.clave, s.descripcion, s.tercero, s.nit, s.motivo,
                           s.reconocido, guardados.pop(s.clave, None)))
    # Se conservan los manuales y los sugeridos ya marcados que dejaron de sugerirse.
    for g in guardados.values():
        if g.manual or g.estado != EstadoDocumento.PENDIENTE:
            salida.append(leer(g.clave, g.descripcion, g.tercero, g.nit, g.motivo,
                               True, g))
    return salida


def _archivos_por_documento(
    session: Session, ids: List[int]
) -> Dict[int, List[ArchivoDocumento]]:
    if not ids:
        return {}
    adjuntos = session.exec(
        select(Adjunto).where(
            Adjunto.entidad_tipo == TipoEntidadAdjunto.DOCUMENTO_SOLICITADO,
            Adjunto.entidad_id.in_(ids),
        ).order_by(Adjunto.id)
    ).all()
    salida: Dict[int, List[ArchivoDocumento]] = {}
    for a in adjuntos:
        salida.setdefault(a.entidad_id, []).append(ArchivoDocumento(
            id=a.id, nombre_original=a.nombre_original,
            tamano_bytes=a.tamano_bytes, creado_en=a.creado_en,
        ))
    return salida


def _mensaje_solicitud(nombre: str, anio: int, pendientes: List[DocumentoLeer]) -> str:
    if not pendientes:
        return ""
    lineas = [
        f"Hola, {nombre.split()[0].title()}:",
        "",
        f"Para preparar su declaración de renta del año gravable {anio} necesito "
        f"los siguientes documentos:",
        "",
    ]
    for i, d in enumerate(pendientes, 1):
        de = f" — {d.tercero.title()}" if d.tercero else ""
        lineas.append(f"{i}. {d.descripcion}{de}")
    lineas += ["", "Pueden ser en PDF o foto legible. Quedo atento. Gracias."]
    return "\n".join(lineas)


def solicitud_documentos(
    session: Session, contador_id: int, contribuyente_id: int, periodo_id: int
) -> SolicitudDocumentosLeer:
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_id)
    docs = _documentos(session, contribuyente_id, periodo)
    pendientes = [d for d in docs if d.estado == EstadoDocumento.PENDIENTE]

    def cuantos(estado: EstadoDocumento) -> int:
        return sum(1 for d in docs if d.estado == estado)

    return SolicitudDocumentosLeer(
        documentos=docs,
        pendientes=len(pendientes),
        recibidos=cuantos(EstadoDocumento.RECIBIDO),
        mensaje=_mensaje_solicitud(contribuyente.nombre, periodo.anio_gravable, pendientes),
        no_aplica=cuantos(EstadoDocumento.NO_APLICA),
        no_lo_tengo=cuantos(EstadoDocumento.NO_LO_TENGO),
        no_entiendo=cuantos(EstadoDocumento.NO_ENTIENDO),
        sin_reconocer=sum(
            1 for d in docs
            if not d.reconocido and d.estado == EstadoDocumento.PENDIENTE
        ),
    )


def fila_del_documento(
    session: Session, contribuyente_id: int, periodo: PeriodoFiscal, clave: str
) -> DocumentoSolicitado:
    """La fila de un documento, creándola si todavía no existe.

    La lista de documentos se deriva al vuelo y la tabla es solo la capa de lo
    que alguien decidió o cargó, así que la fila nace la primera vez que hay
    algo que guardar sobre ese documento.
    """
    actual = {d.clave: d for d in _documentos(session, contribuyente_id, periodo)}
    if clave not in actual:
        raise DocumentoNoEncontradoError(f"No hay un documento «{clave}» en esta solicitud")
    guardado = session.exec(select(DocumentoSolicitado).where(
        DocumentoSolicitado.periodo_fiscal_id == periodo.id,
        DocumentoSolicitado.clave == clave)).first()
    if guardado is None:
        d = actual[clave]
        guardado = DocumentoSolicitado(
            periodo_fiscal_id=periodo.id, clave=clave, descripcion=d.descripcion,
            tercero=d.tercero, nit=d.nit, motivo=d.motivo)
        session.add(guardado)
        session.flush()
    return guardado


def _aplicar_cambios(
    guardado: DocumentoSolicitado,
    cambios: DocumentoActualizar,
    por_contribuyente: bool,
) -> None:
    if cambios.estado is not None:
        guardado.estado = cambios.estado
        guardado.actualizado_en = _hoy()
        guardado.respondido_por_contribuyente = por_contribuyente
    if cambios.nota is not None:
        guardado.nota = cambios.nota
    if cambios.valor_informado is not None:
        guardado.valor_informado = cambios.valor_informado


def actualizar_documento(
    session: Session, contador_id: int, contribuyente_id: int, periodo_id: int,
    clave: str, cambios: DocumentoActualizar,
) -> SolicitudDocumentosLeer:
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_id)
    guardado = fila_del_documento(session, contribuyente_id, periodo, clave)
    _aplicar_cambios(guardado, cambios, por_contribuyente=False)
    session.add(guardado)
    session.commit()
    return solicitud_documentos(session, contador_id, contribuyente_id, periodo_id)


def responder_documento(
    session: Session, contribuyente_id: int, periodo: PeriodoFiscal,
    clave: str, cambios: DocumentoActualizar,
) -> DocumentoLeer:
    """La respuesta del contribuyente desde su enlace de carga.

    No recibe `contador_id`: el alcance lo da el enlace, no un parámetro que
    el cliente pueda cambiar. Devuelve solo el documento tocado, no la
    solicitud completa, porque el mensaje para el cliente y los totales del
    contador no son asunto suyo.
    """
    guardado = fila_del_documento(session, contribuyente_id, periodo, clave)
    _aplicar_cambios(guardado, cambios, por_contribuyente=True)
    session.add(guardado)
    session.commit()
    return next(
        d for d in _documentos(session, contribuyente_id, periodo) if d.clave == clave
    )


def adjuntar_a_documento(
    session: Session, contador_id: int, contribuyente_id: int,
    periodo: PeriodoFiscal, clave: str, flujo, nombre, descripcion=None,
    por_contribuyente: bool = False,
):
    """Sube un soporte y lo deja atado a su documento.

    Subir el papel ES recibir el documento, así que el estado pasa a RECIBIDO
    solo. Pedirle además al cliente que marque un estado después de cargar el
    archivo sería preguntarle dos veces lo mismo.
    """
    from ..adjuntos.modelos import CategoriaAdjunto
    from ..adjuntos.servicios import adjuntar_archivo

    guardado = fila_del_documento(session, contribuyente_id, periodo, clave)
    adjunto = adjuntar_archivo(
        session, contador_id, contribuyente_id,
        TipoEntidadAdjunto.DOCUMENTO_SOLICITADO, guardado.id,
        flujo, nombre, CategoriaAdjunto.CERTIFICADO, descripcion,
    )
    guardado.estado = EstadoDocumento.RECIBIDO
    guardado.actualizado_en = _hoy()
    guardado.respondido_por_contribuyente = por_contribuyente
    session.add(guardado)
    session.commit()
    return adjunto


def documentos_del_periodo(
    session: Session, contribuyente_id: int, periodo: PeriodoFiscal
) -> List[DocumentoLeer]:
    return _documentos(session, contribuyente_id, periodo)


def agregar_documento(
    session: Session, contador_id: int, contribuyente_id: int, periodo_id: int,
    datos: DocumentoCrear,
) -> SolicitudDocumentosLeer:
    obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_id)
    existentes = session.exec(select(DocumentoSolicitado.clave).where(
        DocumentoSolicitado.periodo_fiscal_id == periodo_id,
        DocumentoSolicitado.manual == True,  # noqa: E712
    )).all()
    session.add(DocumentoSolicitado(
        periodo_fiscal_id=periodo_id, clave=f"MANUAL:{len(existentes) + 1}",
        descripcion=datos.descripcion, tercero=datos.tercero, motivo=datos.motivo,
        manual=True))
    session.commit()
    return solicitud_documentos(session, contador_id, contribuyente_id, periodo_id)


# Presentación y declaración anterior


def _como_texto(casillas: Dict[int, Decimal]) -> Dict[str, str]:
    return {str(k): str(v) for k, v in sorted(casillas.items())}


def registrar_presentacion(
    session: Session, contador_id: int, contribuyente_id: int, periodo_id: int,
    datos: PresentacionRegistrar,
) -> DeclaracionPresentada:
    """Guarda copia de la liquidación presentada. La primera es la inicial; las
    siguientes, correcciones.
    """
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_id)
    previas = _presentaciones(session, periodo_id)
    if previas and datos.fecha_presentacion < previas[-1].fecha_presentacion:
        raise DatosInvalidosError(
            "La corrección no puede tener fecha anterior a la última declaración "
            f"presentada ({previas[-1].fecha_presentacion.isoformat()}).")
    # Fecha antes de liquidar: si no, la sanción se calcula a hoy.
    if not previas:
        periodo.fecha_presentacion = datos.fecha_presentacion
        session.add(periodo)
        session.flush()
    liq = liquidacion.liquidar_periodo(session, contador_id, contribuyente_id, periodo_id)
    casillas = construir_casillas(liq.renglones)
    declaracion = DeclaracionPresentada(
        periodo_fiscal_id=periodo_id, fecha_presentacion=datos.fecha_presentacion,
        numero_formulario=datos.numero_formulario, es_correccion=bool(previas),
        origen="APP", casillas=_como_texto(casillas))
    session.add(declaracion)
    session.commit()
    session.refresh(declaracion)
    return declaracion


def registrar_declaracion_anterior(
    session: Session, contador_id: int, contribuyente_id: int,
    datos: DeclaracionAnteriorRegistrar,
) -> DeclaracionPresentada:
    """Registra una declaración hecha fuera de la app. Crea el periodo cerrado si no existe."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    desconocidas = sorted(n for n in datos.casillas if n not in CASILLAS_2024)
    if desconocidas:
        raise DatosInvalidosError(
            f"Casillas que no existen en el formulario 210: {desconocidas}")
    periodo = session.exec(select(PeriodoFiscal).where(
        PeriodoFiscal.contribuyente_id == contribuyente_id,
        PeriodoFiscal.anio_gravable == datos.anio_gravable)).first()
    if periodo is None:
        periodo = PeriodoFiscal(
            contribuyente_id=contribuyente_id, anio_gravable=datos.anio_gravable,
            estado=EstadoPeriodo.CERRADO, fecha_presentacion=datos.fecha_presentacion)
        session.add(periodo)
        session.flush()
    previas = _presentaciones(session, periodo.id)
    declaracion = DeclaracionPresentada(
        periodo_fiscal_id=periodo.id, fecha_presentacion=datos.fecha_presentacion,
        numero_formulario=datos.numero_formulario, es_correccion=bool(previas),
        origen="MANUAL", casillas=_como_texto(datos.casillas))
    session.add(declaracion)
    if periodo.fecha_presentacion is None:
        periodo.fecha_presentacion = datos.fecha_presentacion
        session.add(periodo)
    session.commit()
    session.refresh(declaracion)
    return declaracion


def traer_datos_del_anio_anterior(
    session: Session, contador_id: int, contribuyente_id: int, periodo_id: int
) -> List[str]:
    """Trae de la declaración anterior: 126 (anticipo), 133 -> 130, 137 -> 131.
    Devuelve lo que cambió.
    """
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_id)
    anterior = declaracion_vigente(session, contribuyente_id, periodo.anio_gravable - 1)
    if anterior is None:
        raise DatosInvalidosError(
            f"No hay declaración registrada del año {periodo.anio_gravable - 1}.")
    c = _casillas_de(anterior)
    hoja = liquidacion.obtener_hoja(session, contador_id, contribuyente_id, periodo_id)
    cambios: List[str] = []
    for campo, casilla, nombre in (
        ("impuesto_neto_anio_anterior", 126, "Impuesto neto de renta del año anterior"),
        ("anticipo_pagado_anio_anterior", 133, "Anticipo liquidado el año anterior"),
        ("saldo_a_favor_anio_anterior", 137, "Saldo a favor del año anterior"),
    ):
        valor = c.get(casilla, CERO)
        if Decimal(getattr(hoja, campo) or 0) != valor:
            setattr(hoja, campo, valor)
            cambios.append(f"{nombre}: {pesos(valor)} (casilla {casilla})")
    session.add(hoja)
    session.commit()
    return cambios


# Seguimiento


def actualizar_seguimiento(
    session: Session, contador_id: int, contribuyente_id: int, periodo_id: int,
    cambios: SeguimientoActualizar,
) -> None:
    obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_id)
    s = _seguimiento(session, periodo_id)
    for campo, valor in cambios.model_dump(exclude_unset=True).items():
        setattr(s, campo, valor if valor is not None or campo != "notas" else "")
    session.add(s)
    session.commit()


def etapas(
    tiene_exogena: bool,
    documentos_total: int,
    documentos_pendientes: int,
    seguimiento: SeguimientoDeclaracion,
    fecha_presentacion: Optional[date],
    saldo_a_pagar: Optional[Decimal],
    documentos_no_entiendo: int = 0,
    documentos_no_lo_tengo: int = 0,
    documentos_sin_reconocer: int = 0,
) -> ProcesoLeer:
    """Etapas en orden de trabajo. Exógena, documentos y presentación se calculan;
    el resto lo marca el contador.
    """
    s = seguimiento
    sin_saldo = saldo_a_pagar is not None and saldo_a_pagar <= 0
    lista = [
        EtapaLeer(clave="EXOGENA", nombre="Exógena cargada", accion="Cargar la exógena", automatica=True,
                  hecha=tiene_exogena,
                  detalle="" if tiene_exogena else "Descargue el reporte de la DIAN y cárguelo"),
        EtapaLeer(clave="DOCUMENTOS", nombre="Documentos del cliente", accion="Recibir los documentos del cliente", automatica=True,
                  hecha=documentos_total > 0 and documentos_pendientes == 0,
                  detalle=(f"Faltan {documentos_pendientes} de {documentos_total}"
                           if documentos_pendientes else "")),
        EtapaLeer(clave="CRUCE", nombre="Cruce con la DIAN revisado", accion="Revisar el cruce con la DIAN", automatica=False,
                  hecha=s.cruce_revisado_en is not None, fecha=s.cruce_revisado_en),
        EtapaLeer(clave="LIQUIDACION", nombre="Liquidación revisada", accion="Revisar la liquidación", automatica=False,
                  hecha=s.liquidacion_revisada_en is not None,
                  fecha=s.liquidacion_revisada_en),
        EtapaLeer(clave="APROBACION", nombre="Aprobada por el cliente", accion="Obtener la aprobación del cliente", automatica=False,
                  hecha=s.aprobada_cliente_en is not None, fecha=s.aprobada_cliente_en),
        EtapaLeer(clave="PRESENTADA", nombre="Presentada ante la DIAN", accion="Presentar ante la DIAN", automatica=True,
                  hecha=fecha_presentacion is not None, fecha=fecha_presentacion),
        EtapaLeer(clave="PAGO", nombre="Pagada", accion="Registrar el pago", automatica=False,
                  hecha=s.pagada_en is not None or (sin_saldo and fecha_presentacion is not None),
                  fecha=s.pagada_en,
                  detalle="Sin saldo a pagar" if sin_saldo and s.pagada_en is None else ""),
    ]
    actual = next((e.clave for e in lista if not e.hecha), None)
    return ProcesoLeer(etapas=lista, etapa_actual=actual,
                       hechas=sum(e.hecha for e in lista), total=len(lista),
                       documentos_pendientes=documentos_pendientes,
                       documentos_no_entiendo=documentos_no_entiendo,
                       documentos_no_lo_tengo=documentos_no_lo_tengo,
                       documentos_sin_reconocer=documentos_sin_reconocer)


def contar_documentos(docs: List[DocumentoLeer]) -> Dict[str, int]:
    """Los conteos que miran la cartera y el panel del proceso."""
    return {
        "pendientes": sum(d.estado == EstadoDocumento.PENDIENTE for d in docs),
        "no_entiendo": sum(d.estado == EstadoDocumento.NO_ENTIENDO for d in docs),
        "no_lo_tengo": sum(d.estado == EstadoDocumento.NO_LO_TENGO for d in docs),
        "sin_reconocer": sum(
            not d.reconocido and d.estado == EstadoDocumento.PENDIENTE for d in docs
        ),
    }


def proceso_resumido(
    session: Session, contribuyente_id: int, periodo: PeriodoFiscal
) -> ProcesoLeer:
    """Etapas sin liquidar, para la cartera."""
    tiene_exogena = session.exec(select(ReporteExogena.id).where(
        ReporteExogena.periodo_fiscal_id == periodo.id)).first() is not None
    docs = _documentos(session, contribuyente_id, periodo)
    presentadas = _presentaciones(session, periodo.id)
    saldo = _casillas_de(presentadas[-1]).get(136) if presentadas else None
    c = contar_documentos(docs)
    return etapas(tiene_exogena, len(docs), c["pendientes"],
                  _seguimiento(session, periodo.id), periodo.fecha_presentacion, saldo,
                  c["no_entiendo"], c["no_lo_tengo"], c["sin_reconocer"])


# Vista completa


def _intereses_leer(r: calculos.Intereses, fecha_pago: date, pagado: bool) -> InteresesLeer:
    return InteresesLeer(
        capital=r.capital, fecha_pago=fecha_pago, pagado=pagado, valor=r.valor,
        dias=r.dias,
        tramos=[TramoInteresLeer(desde=t.desde, hasta=t.hasta, dias=t.dias,
                                 tasa_efectiva_anual=(t.tasa * CIEN).quantize(Decimal("0.01")),
                                 interes=t.interes) for t in r.tramos],
        meses_sin_tasa=[f"{a}-{m:02d}" for a, m in r.meses_sin_tasa],
        formula=r.formula, fuente=r.fuente,
    )


def gestion(
    session: Session, contador_id: int, contribuyente_id: int, periodo_id: int,
    fecha_pago: Optional[date] = None,
) -> GestionLeer:
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_id)
    hoy = _hoy()
    avisos: List[str] = []

    liq = liquidacion.liquidar_periodo(session, contador_id, contribuyente_id, periodo_id)
    vivas = construir_casillas(liq.renglones)
    presentadas = _presentaciones(session, periodo_id)
    vigente = _casillas_de(presentadas[-1]) if presentadas else None
    # Se usa lo presentado; si no hay, lo liquidado.
    base = vigente if vigente is not None else vivas
    saldo_a_pagar, saldo_a_favor = base.get(136, CERO), base.get(137, CERO)

    vencimiento = _vencimiento(session, contribuyente.rut, periodo)
    if vencimiento is None:
        avisos.append("No hay fecha de vencimiento: cargue el calendario de la DIAN "
                      "en Parámetros o fije una fecha manual en el seguimiento.")
    seguimiento = _seguimiento(session, periodo_id)
    docs = _documentos(session, contribuyente_id, periodo)
    tiene_exogena = session.exec(select(ReporteExogena.id).where(
        ReporteExogena.periodo_fiscal_id == periodo_id)).first() is not None
    c = contar_documentos(docs)
    proceso = etapas(tiene_exogena, len(docs), c["pendientes"],
                     seguimiento, periodo.fecha_presentacion,
                     saldo_a_pagar if presentadas else None,
                     c["no_entiendo"], c["no_lo_tengo"], c["sin_reconocer"])

    # Declaración anterior y comparativo
    anterior_decl = declaracion_vigente(session, contribuyente_id, periodo.anio_gravable - 1)
    comparativo = None
    if anterior_decl is not None:
        anterior = _casillas_de(anterior_decl)
        uvt = _uvt(periodo.anio_gravable, liq.parametros.uvt)
        comp = calculos.comparar_con_anterior(
            base, anterior, umbral_minimo=uvt * 20,
            anterior_incompleto=anterior_decl.origen == "MANUAL")
        comparativo = ComparativoLeer(
            anio_anterior=periodo.anio_gravable - 1,
            origen_anterior=("Registrada a mano" if anterior_decl.origen == "MANUAL"
                             else "Presentada desde la app"),
            filas=[FilaComparativoLeer(
                casilla=f.casilla,
                nombre=CASILLAS_2024[f.casilla].nombre if f.casilla in CASILLAS_2024 else "",
                anterior=f.anterior, actual=f.actual, diferencia=f.diferencia,
                variacion_porcentaje=(f.variacion * CIEN).quantize(Decimal("0.1"))
                if f.variacion is not None else None,
                revisar=f.revisar) for f in comp.filas],
            coherencias=[CoherenciaLeer(**c.__dict__) for c in comp.coherencias],
        )

    # Beneficio de auditoría
    hoja = session.get(HojaLiquidacion, periodo_id)
    impuesto_anterior = None
    if anterior_decl is not None:
        impuesto_anterior = _casillas_de(anterior_decl).get(126, CERO)
    elif hoja is not None and hoja.impuesto_neto_anio_anterior:
        impuesto_anterior = Decimal(hoja.impuesto_neto_anio_anterior)
    presentada_a_tiempo = (
        None if periodo.fecha_presentacion is None or vencimiento is None
        else periodo.fecha_presentacion <= vencimiento)
    if seguimiento.pagada_en is not None and vencimiento is not None:
        pagada_a_tiempo = seguimiento.pagada_en <= vencimiento
    elif presentadas and saldo_a_pagar <= 0:
        pagada_a_tiempo = True
    else:
        pagada_a_tiempo = None
    b = calculos.calcular_beneficio_auditoria(
        periodo.anio_gravable, base.get(126, CERO), impuesto_anterior,
        _uvt(periodo.anio_gravable - 1, liq.parametros.uvt),
        presentada_a_tiempo, pagada_a_tiempo,
    )
    beneficio = BeneficioLeer(
        vigente=b.vigente, meses=b.meses,
        incremento_porcentaje=(b.incremento * CIEN).quantize(Decimal("0.1"))
        if b.incremento is not None else None,
        impuesto_actual=b.impuesto_actual, impuesto_anterior=b.impuesto_anterior,
        impuesto_para_12_meses=b.impuesto_para_12_meses,
        impuesto_para_6_meses=b.impuesto_para_6_meses,
        condiciones=[CondicionLeer(**c.__dict__) for c in b.condiciones],
        conclusion=b.conclusion, fuente=b.fuente,
    )

    # Firmeza
    perdidas = any(base.get(n, CERO) > 0 for n in (55, 56, 71, 72, 88, 89))
    f = calculos.calcular_firmeza(
        vencimiento, periodo.fecha_presentacion,
        tiene_saldo_a_favor=saldo_a_favor > 0,
        solicitud_devolucion=seguimiento.solicitud_devolucion_en,
        liquida_o_compensa_perdidas=perdidas,
        meses_beneficio_auditoria=b.meses if b.meses and pagada_a_tiempo else None,
    )
    if len(presentadas) > 1:
        f.notas.append("La declaración se corrigió: el término de firmeza sigue "
                       "contándose desde la declaración inicial.")
    firmeza = FirmezaLeer(fecha=f.fecha, regla=f.regla, fuente=f.fuente, notas=f.notas)

    # Corrección
    tasas = _tasas(session)
    correccion = None
    if vigente is not None:
        c = calculos.calcular_correccion(
            vigente.get(136, CERO), vigente.get(137, CERO),
            vivas.get(136, CERO), vivas.get(137, CERO),
            vencimiento, presentadas[0].fecha_presentacion, hoy,
            _uvt(hoy.year, liq.parametros.uvt),
            despues_de_emplazamiento=seguimiento.emplazamiento_notificado,
            reduccion=hoja.reduccion_sancion.value if hoja is not None else "NINGUNA",
        )
        if c.tipo != "SIN_EFECTO" or vivas != vigente:
            intereses_corr = None
            if c.tipo == "AUMENTA" and vencimiento is not None:
                # Intereses sobre el mayor impuesto (134), no sobre sanciones.
                mayor_impuesto = vivas.get(134, CERO) - vigente.get(134, CERO)
                r = calculos.calcular_intereses(mayor_impuesto, vencimiento, hoy, tasas)
                intereses_corr = _intereses_leer(r, hoy, False)
            correccion = CorreccionLeer(
                tipo=c.tipo, mayor_valor=c.mayor_valor, sancion=c.sancion,
                plazo=c.plazo, vencida=c.vencida, formula=c.formula, fuente=c.fuente,
                notas=c.notas, intereses=intereses_corr,
                total_a_pagar=(max(c.mayor_valor, CERO) + c.sancion
                               + (intereses_corr.valor if intereses_corr else CERO)),
            )

    # Intereses de mora
    intereses = None
    capital = base.get(134, saldo_a_pagar)
    if vencimiento is not None and capital > 0:
        pagado = seguimiento.pagada_en is not None
        corte = seguimiento.pagada_en or fecha_pago or hoy
        if corte > vencimiento:
            r = calculos.calcular_intereses(capital, vencimiento, corte, tasas)
            intereses = _intereses_leer(r, corte, pagado)
            if r.meses_sin_tasa:
                avisos.append(
                    "Falta la tasa de interés moratorio de "
                    + ", ".join(intereses.meses_sin_tasa)
                    + ": cárguela en Parámetros DIAN para completar el cálculo.")

    return GestionLeer(
        anio_gravable=periodo.anio_gravable, vencimiento=vencimiento,
        fecha_presentacion=periodo.fecha_presentacion,
        saldo_a_pagar=saldo_a_pagar, saldo_a_favor=saldo_a_favor,
        proceso=proceso,
        seguimiento=SeguimientoActualizar(**seguimiento.model_dump(
            exclude={"periodo_fiscal_id"})),
        presentaciones=[_leer_presentada(d, periodo.anio_gravable) for d in presentadas],
        declaracion_anterior=_leer_presentada(anterior_decl, periodo.anio_gravable - 1)
        if anterior_decl else None,
        comparativo=comparativo, beneficio_auditoria=beneficio, firmeza=firmeza,
        correccion=correccion, intereses=intereses, avisos=avisos,
    )


# Tasas de interés moratorio

FUENTE_TABLA_DIAN = ("DIAN, tabla «Tasa de interés moratorio» publicada el "
                     "31-08-2026 (dian.gov.co/normatividad/TIM)")

# Tasas publicadas por la DIAN, % efectivo anual.
TASAS_OFICIALES = {
    (2025, 1): "22.89", (2025, 2): "24.30", (2025, 3): "22.92", (2025, 4): "23.62",
    (2025, 5): "23.97", (2025, 6): "23.55", (2025, 7): "22.78", (2025, 8): "23.17",
    (2025, 9): "23.01", (2025, 10): "22.36", (2025, 11): "22.99", (2025, 12): "23.02",
    (2026, 1): "22.36", (2026, 2): "23.23", (2026, 3): "23.52", (2026, 4): "24.76",
    (2026, 5): "26.17", (2026, 6): "26.79", (2026, 7): "26.79", (2026, 8): "27.66",
    (2026, 9): "27.24",
}

# Meses aún no publicados en la tabla de la DIAN, con su fuente.
TASAS_CON_OTRA_FUENTE = {
    (2026, 10): ("26.59", "Usura de consumo 28,59 % (Superfinanciera, Resolución 1472 "
                          "del 30-09-2026) menos 2 puntos"),
}




def _tasas_publicadas() -> Dict[Tuple[int, int], TasaInteresMoratorio]:
    todas = {k: (v, FUENTE_TABLA_DIAN) for k, v in TASAS_OFICIALES.items()}
    todas.update(TASAS_CON_OTRA_FUENTE)
    return {(a, m): TasaInteresMoratorio(anio=a, mes=m, tasa_efectiva_anual=Decimal(t),
                                         fuente=f)
            for (a, m), (t, f) in todas.items()}


def listar_tasas(session: Session) -> List[TasaInteresMoratorio]:
    """Tasas oficiales completadas o corregidas por las de la base."""
    tasas = _tasas_publicadas()
    for t in session.exec(select(TasaInteresMoratorio)).all():
        tasas[(t.anio, t.mes)] = t
    return sorted(tasas.values(), key=lambda t: (t.anio, t.mes), reverse=True)


def guardar_tasa(session: Session, datos: TasaInteresDatos) -> TasaInteresMoratorio:
    tasa = session.get(TasaInteresMoratorio, (datos.anio, datos.mes))
    if tasa is None:
        tasa = TasaInteresMoratorio(anio=datos.anio, mes=datos.mes,
                                    tasa_efectiva_anual=datos.tasa_efectiva_anual)
    tasa.tasa_efectiva_anual = datos.tasa_efectiva_anual
    tasa.fuente = datos.fuente
    session.add(tasa)
    session.commit()
    session.refresh(tasa)
    return tasa
