"""Servicios del portal de carga.

El enlace **solo escribe**: ni la liquidación ni la conciliación ni la cartera
salen por él. Antes eso se sostenía por los imports de este archivo, pero la
lista de documentos ahora viene de `gestion`, que sí lee la liquidación para
saber qué pedir. Así que la garantía dejó de ser «qué está importado» y pasó a
ser «qué puede devolver»: `test_portal` recorre el esquema de todas las
respuestas de `/carga/...` y falla si alguna arrastra un campo de liquidación.
Es una garantía más fuerte, porque sobrevive a que alguien agregue un import.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import BinaryIO, Dict, List, Optional

from sqlmodel import Session, select

from core.excepciones import (
    AnioGravableNoSoportadoError,
    DatoAdicionalNoEncontradoError,
    EnlaceCargaExpiradoError,
    EnlaceCargaNoEncontradoError,
    EnlaceCargaRevocadoError,
    PeriodoFiscalCerradoError,
    PoliticaNoAceptadaError,
    TopeAdicionalExcedidoError,
    VersionPoliticaDesconocidaError,
)

from ..contadores.modelos import Contador
from ..contribuyentes.modelos import Contribuyente, EstadoPeriodo, PeriodoFiscal
from ..contribuyentes.servicios import obtener_contribuyente, obtener_periodo_fiscal
from ..exogena.modelos import ReporteExogena
from ..exogena.servicios import importar_reporte_exogena
from ..gestion import servicios as gestion
from ..gestion.modelos import DocumentoActualizar, DocumentoLeer
from ..parametros.tablas_oficiales import ANIOS_SOPORTADOS, PARAMETROS_POR_ANIO
from . import politica
from .modelos import (
    AceptarPolitica,
    AutorizacionLeer,
    AutorizacionTratamiento,
    DatoAdicional,
    DatoAdicionalCrear,
    DatoAdicionalLeer,
    EnlaceCarga,
    EnlaceCargaCreado,
    EnlaceCargaCrear,
    EnlaceCargaLeer,
    ParametroAdicional,
    ParametrosAdicionales,
    PoliticaLeer,
    ResultadoCargaExogena,
    SesionPortal,
    TipoAdicional,
)

# Ruta del portal en el frontend. El backend solo devuelve la ruta relativa:
# la dirección pública del despliegue no la conoce (ni debe inventarla), así
# que el cliente la completa con su propio origen.
RUTA_PORTAL = "/carga"

LONGITUD_PREFIJO = 8


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(valor: Optional[datetime]) -> Optional[datetime]:
    """Algunos motores devuelven la fecha sin zona; comparar así no falla."""
    if valor is None or valor.tzinfo is not None:
        return valor
    return valor.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------


def generar_token() -> str:
    """256 bits de entropía. No es adivinable ni enumerable."""
    return secrets.token_urlsafe(32)


def hashear_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Enlaces: lado del contador
# ---------------------------------------------------------------------------


def _a_lectura_enlace(
    session: Session, enlace: EnlaceCarga, anio_gravable: Optional[int] = None
) -> EnlaceCargaLeer:
    if anio_gravable is None:
        periodo = session.get(PeriodoFiscal, enlace.periodo_fiscal_id)
        anio_gravable = periodo.anio_gravable if periodo else None
    autorizacion = _autorizacion_vigente(session, enlace)
    return EnlaceCargaLeer(
        id=enlace.id,
        contribuyente_id=enlace.contribuyente_id,
        periodo_fiscal_id=enlace.periodo_fiscal_id,
        anio_gravable=anio_gravable,
        prefijo=enlace.prefijo,
        creado_en=enlace.creado_en,
        expira_en=enlace.expira_en,
        revocado_en=enlace.revocado_en,
        ultimo_acceso_en=enlace.ultimo_acceso_en,
        nota=enlace.nota,
        vigente=esta_vigente(enlace),
        politica_aceptada=autorizacion is not None,
        version_politica_aceptada=autorizacion.version_politica if autorizacion else None,
        politica_aceptada_en=autorizacion.aceptada_en if autorizacion else None,
    )


def esta_vigente(enlace: EnlaceCarga) -> bool:
    if enlace.revocado_en is not None:
        return False
    return _aware(enlace.expira_en) > _ahora()


def crear_enlace(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    datos: EnlaceCargaCrear,
) -> EnlaceCargaCreado:
    """Genera el enlace y revoca los anteriores del mismo periodo.

    Lo segundo es deliberado: si generar un enlace nuevo dejara vivos los
    viejos, cada reenvío por WhatsApp sumaría una puerta abierta que nadie
    recuerda cerrar. Un periodo, un enlace válido.
    """
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, datos.periodo_fiscal_id
    )
    if periodo.estado == EstadoPeriodo.CERRADO:
        raise PeriodoFiscalCerradoError(
            f"El periodo fiscal {periodo.anio_gravable} está cerrado: no tiene "
            "sentido pedirle más soportes al contribuyente"
        )

    anteriores = session.exec(
        select(EnlaceCarga).where(
            EnlaceCarga.contribuyente_id == contribuyente_id,
            EnlaceCarga.periodo_fiscal_id == periodo.id,
            EnlaceCarga.revocado_en.is_(None),
        )
    ).all()
    for anterior in anteriores:
        anterior.revocado_en = _ahora()
        session.add(anterior)

    token = generar_token()
    enlace = EnlaceCarga(
        token_hash=hashear_token(token),
        prefijo=token[:LONGITUD_PREFIJO],
        contador_id=contador_id,
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo.id,
        expira_en=_ahora() + timedelta(days=datos.dias_vigencia),
        nota=(datos.nota or "").strip() or None,
    )
    session.add(enlace)
    session.commit()
    session.refresh(enlace)

    lectura = _a_lectura_enlace(session, enlace, periodo.anio_gravable)
    return EnlaceCargaCreado(
        **lectura.model_dump(),
        token=token,
        ruta=f"{RUTA_PORTAL}/{token}",
    )


def listar_enlaces(
    session: Session, contador_id: int, contribuyente_id: int
) -> List[EnlaceCargaLeer]:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    enlaces = session.exec(
        select(EnlaceCarga)
        .where(EnlaceCarga.contribuyente_id == contribuyente_id)
        .order_by(EnlaceCarga.creado_en.desc(), EnlaceCarga.id.desc())
    ).all()
    return [_a_lectura_enlace(session, e) for e in enlaces]


def obtener_enlace(
    session: Session, contador_id: int, contribuyente_id: int, enlace_id: int
) -> EnlaceCarga:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    enlace = session.get(EnlaceCarga, enlace_id)
    if enlace is None or enlace.contribuyente_id != contribuyente_id:
        raise EnlaceCargaNoEncontradoError(
            f"No existe el enlace de carga {enlace_id} para el contribuyente "
            f"{contribuyente_id}"
        )
    return enlace


def revocar_enlace(
    session: Session, contador_id: int, contribuyente_id: int, enlace_id: int
) -> EnlaceCargaLeer:
    enlace = obtener_enlace(session, contador_id, contribuyente_id, enlace_id)
    if enlace.revocado_en is None:
        enlace.revocado_en = _ahora()
        session.add(enlace)
        session.commit()
        session.refresh(enlace)
    return _a_lectura_enlace(session, enlace)


# ---------------------------------------------------------------------------
# Enlaces: lado público (token)
# ---------------------------------------------------------------------------


def resolver_enlace(session: Session, token: str, registrar_acceso: bool = True) -> EnlaceCarga:
    """Del token al enlace. Distingue «no existe» de «ya no sirve».

    Decirle «este enlace fue revocado» a quien tiene el token correcto no
    filtra nada —ya lo tenía— y le ahorra al contribuyente llamar al contador
    para preguntar por qué la página no carga.
    """
    enlace = session.exec(
        select(EnlaceCarga).where(EnlaceCarga.token_hash == hashear_token(token or ""))
    ).first()
    if enlace is None:
        raise EnlaceCargaNoEncontradoError("El enlace no existe o ya no es válido")
    if enlace.revocado_en is not None:
        raise EnlaceCargaRevocadoError(
            "Su contador desactivó este enlace. Pídale uno nuevo."
        )
    if _aware(enlace.expira_en) <= _ahora():
        raise EnlaceCargaExpiradoError(
            "Este enlace venció. Pídale a su contador uno nuevo; lo que ya "
            "cargó no se pierde."
        )
    if registrar_acceso:
        enlace.ultimo_acceso_en = _ahora()
        session.add(enlace)
        session.commit()
        session.refresh(enlace)
    return enlace


def periodo_del_enlace(session: Session, enlace: EnlaceCarga) -> PeriodoFiscal:
    return session.get(PeriodoFiscal, enlace.periodo_fiscal_id)


def _autorizacion_vigente(
    session: Session, enlace: EnlaceCarga
) -> Optional[AutorizacionTratamiento]:
    """La aceptación más reciente de este contribuyente, de cualquier enlace.

    Se busca por contribuyente y no por enlace: si el contador tuvo que
    reenviar el enlace, el titular ya autorizó el tratamiento y volver a
    pedírselo sería ruido, no más garantía.
    """
    return session.exec(
        select(AutorizacionTratamiento)
        .where(AutorizacionTratamiento.contribuyente_id == enlace.contribuyente_id)
        .order_by(AutorizacionTratamiento.aceptada_en.desc(), AutorizacionTratamiento.id.desc())
    ).first()


def exigir_politica_aceptada(session: Session, enlace: EnlaceCarga) -> AutorizacionTratamiento:
    autorizacion = _autorizacion_vigente(session, enlace)
    if autorizacion is None:
        raise PoliticaNoAceptadaError(
            "Para cargar información hay que aceptar primero la política de "
            "tratamiento de datos"
        )
    return autorizacion


def _politica_a_lectura(version: politica.VersionPolitica) -> PoliticaLeer:
    return PoliticaLeer(
        version=version.version,
        vigente_desde=version.vigente_desde,
        titulo=version.titulo,
        finalidades=list(version.finalidades),
        responsable=version.responsable,
        derechos=version.derechos,
        texto=version.texto,
    )


def aceptar_politica(
    session: Session,
    enlace: EnlaceCarga,
    datos: AceptarPolitica,
    red_origen: Optional[str] = None,
    agente_usuario: Optional[str] = None,
) -> AutorizacionLeer:
    if not datos.acepto:
        raise PoliticaNoAceptadaError(
            "La autorización tiene que ser expresa: marque la casilla para aceptar"
        )
    version = politica.obtener(datos.version_politica)
    if version is None:
        raise VersionPoliticaDesconocidaError(
            f"La versión «{datos.version_politica}» de la política no existe. "
            "Recargue la página para leer la versión vigente."
        )

    autorizacion = AutorizacionTratamiento(
        contribuyente_id=enlace.contribuyente_id,
        enlace_carga_id=enlace.id,
        version_politica=version.version,
        nombre_quien_acepta=datos.nombre_quien_acepta.strip(),
        documento_quien_acepta=(datos.documento_quien_acepta or "").strip() or None,
        red_origen=red_origen,
        agente_usuario=(agente_usuario or "")[:300] or None,
    )
    session.add(autorizacion)
    session.commit()
    session.refresh(autorizacion)
    return AutorizacionLeer(
        version_politica=autorizacion.version_politica,
        aceptada_en=autorizacion.aceptada_en,
        nombre_quien_acepta=autorizacion.nombre_quien_acepta,
        documento_quien_acepta=autorizacion.documento_quien_acepta,
    )


def _enmascarar(documento: str) -> str:
    digitos = "".join(c for c in (documento or "") if c.isdigit())
    if len(digitos) <= 4:
        return "•" * len(digitos)
    return "•" * (len(digitos) - 4) + digitos[-4:]


def _reporte_vigente(session: Session, periodo_fiscal_id: int) -> Optional[ReporteExogena]:
    return session.exec(
        select(ReporteExogena)
        .where(ReporteExogena.periodo_fiscal_id == periodo_fiscal_id)
        .order_by(ReporteExogena.version.desc(), ReporteExogena.id.desc())
    ).first()


def sesion_portal(session: Session, enlace: EnlaceCarga) -> SesionPortal:
    contribuyente = session.get(Contribuyente, enlace.contribuyente_id)
    periodo = periodo_del_enlace(session, enlace)
    contador = session.get(Contador, enlace.contador_id)
    autorizacion = _autorizacion_vigente(session, enlace)
    reporte = _reporte_vigente(session, enlace.periodo_fiscal_id)

    return SesionPortal(
        contribuyente_nombre=contribuyente.nombre if contribuyente else "",
        documento_enmascarado=_enmascarar(contribuyente.rut if contribuyente else ""),
        contador_nombre=contador.nombre if contador else "su contador",
        anio_gravable=periodo.anio_gravable if periodo else 0,
        expira_en=enlace.expira_en,
        politica=_politica_a_lectura(politica.vigente()),
        autorizacion=(
            AutorizacionLeer(
                version_politica=autorizacion.version_politica,
                aceptada_en=autorizacion.aceptada_en,
                nombre_quien_acepta=autorizacion.nombre_quien_acepta,
                documento_quien_acepta=autorizacion.documento_quien_acepta,
            )
            if autorizacion
            else None
        ),
        exogena_cargada=reporte is not None,
        fecha_corte_exogena=reporte.fecha_corte if reporte else None,
        version_exogena=reporte.version if reporte else None,
        documentos=documentos_del_enlace(session, enlace),
        adicionales=listar_adicionales(
            session, enlace.contribuyente_id, enlace.periodo_fiscal_id
        ),
    )


# ---------------------------------------------------------------------------
# Documentos: la lista es la de `gestion`, vista desde el lado del cliente
# ---------------------------------------------------------------------------


def documentos_del_enlace(session: Session, enlace: EnlaceCarga) -> List[DocumentoLeer]:
    return gestion.documentos_del_periodo(
        session, enlace.contribuyente_id, periodo_del_enlace(session, enlace)
    )


def responder_documento_por_enlace(
    session: Session, enlace: EnlaceCarga, clave: str, cambios: DocumentoActualizar
) -> DocumentoLeer:
    exigir_politica_aceptada(session, enlace)
    return gestion.responder_documento(
        session, enlace.contribuyente_id, periodo_del_enlace(session, enlace),
        clave, cambios,
    )


def adjuntar_por_enlace(
    session: Session,
    enlace: EnlaceCarga,
    clave: str,
    flujo: BinaryIO,
    nombre: Optional[str],
    descripcion: Optional[str] = None,
):
    """Sube un soporte y lo deja atado a su documento.

    El archivo nunca queda suelto en «documentos generales»: la entidad del
    adjunto es el documento solicitado, así que el contador abre el ítem y ve
    el papel que lo respalda sin tener que adivinar a qué correspondía.
    """
    exigir_politica_aceptada(session, enlace)
    return gestion.adjuntar_a_documento(
        session, enlace.contador_id, enlace.contribuyente_id,
        periodo_del_enlace(session, enlace), clave, flujo, nombre, descripcion,
        por_contribuyente=True,
    )


# ---------------------------------------------------------------------------
# Carga de la exógena desde el enlace
# ---------------------------------------------------------------------------


def cargar_exogena_por_enlace(
    session: Session, enlace: EnlaceCarga, contenido: bytes, nombre_archivo: str
) -> ResultadoCargaExogena:
    exigir_politica_aceptada(session, enlace)

    # El alcance del enlace es el que decide a dónde entra el archivo: el
    # contribuyente no envía ningún identificador que se pueda manipular.
    importado = importar_reporte_exogena(
        session,
        enlace.contador_id,
        enlace.contribuyente_id,
        enlace.periodo_fiscal_id,
        contenido,
        nombre_archivo,
    )
    reporte = session.get(ReporteExogena, importado.id)

    # No hay nada que sincronizar: la lista de documentos se deriva del
    # reporte cada vez que se consulta, así que cargar un archivo nuevo la
    # actualiza sola y no puede dejar filas obsoletas. Esto solo cuenta lo que
    # quedó pedido, para decírselo al contribuyente.
    documentos = documentos_del_enlace(session, enlace)
    conteo = gestion.contar_documentos(documentos)
    return ResultadoCargaExogena(
        reporte_exogena_id=reporte.id,
        version=reporte.version,
        fecha_corte=reporte.fecha_corte,
        cantidad_registros=importado.cantidad_registros,
        errores_en_filas=len(importado.errores),
        documentos_pedidos=len(documentos),
        sin_reconocer=conteo["sin_reconocer"],
    )


# ---------------------------------------------------------------------------
# Datos adicionales
# ---------------------------------------------------------------------------

# Qué concepto de la tabla de parámetros gobierna el tope de cada tipo. Los
# que no figuran no tienen tope legal propio (un activo o una deuda valen lo
# que valen) y solo se validan como cifras positivas.
_CODIGO_TOPE: Dict[TipoAdicional, str] = {
    TipoAdicional.INTERESES_VIVIENDA: "INTERESES_VIVIENDA",
    TipoAdicional.MEDICINA_PREPAGADA: "MEDICINA_PREPAGADA",
    TipoAdicional.AHORRO_AFC: "AHORRO_AFC",
    TipoAdicional.APORTES_VOLUNTARIOS_PENSION: "APORTES_VOLUNTARIOS_PENSION",
}

ETIQUETAS_ADICIONAL: Dict[TipoAdicional, str] = {
    TipoAdicional.DEPENDIENTE: "Dependientes económicos",
    TipoAdicional.INTERESES_VIVIENDA: "Intereses del crédito de vivienda",
    TipoAdicional.MEDICINA_PREPAGADA: "Medicina prepagada o póliza de salud",
    TipoAdicional.AHORRO_AFC: "Ahorro en cuenta AFC o AVC",
    TipoAdicional.APORTES_VOLUNTARIOS_PENSION: "Aportes voluntarios a pensión",
    TipoAdicional.ACTIVO: "Bien o activo en Colombia",
    TipoAdicional.DEUDA: "Deuda a 31 de diciembre",
    TipoAdicional.BIEN_EXTERIOR: "Bien o inversión en el exterior",
}

_ADVERTENCIA_PORCENTAJE = (
    "Este concepto tiene además un límite porcentual sobre los ingresos del "
    "año, que solo se puede evaluar al liquidar. Aquí se valida el tope en "
    "UVT; el límite porcentual lo aplica el motor."
)

_ADVERTENCIA_DEPENDIENTES = (
    "El número de dependientes que se declara lo fija el contador en la hoja "
    "de liquidación. Lo que se captura aquí es el soporte de cada uno, para "
    "que el contador tenga con qué sustentarlo."
)


def _parametros_del_anio(anio_gravable: int):
    parametros = PARAMETROS_POR_ANIO.get(anio_gravable)
    if parametros is None:
        disponibles = ", ".join(str(a) for a in ANIOS_SOPORTADOS)
        raise AnioGravableNoSoportadoError(
            f"La aplicación no trae los parámetros tributarios de "
            f"{anio_gravable} (disponibles: {disponibles}): no se puede "
            "validar el formulario de adicionales contra topes que no existen"
        )
    return parametros


def _tope_en_pesos(tope, uvt: Decimal) -> Optional[Decimal]:
    if tope is None or tope.tope_uvt is None:
        return None
    factor = Decimal(12) if tope.es_mensual else Decimal(1)
    return (tope.tope_uvt * uvt * factor).quantize(Decimal("0.01"))


def parametros_adicionales(anio_gravable: int) -> ParametrosAdicionales:
    """Los topes del año, para que el formulario y el servidor usen los mismos.

    Salen de `parametros.tablas_oficiales`, que está versionada por año
    gravable y cita la norma de cada cifra. Ningún tope de este formulario
    está escrito en el código del formulario.
    """
    parametros = _parametros_del_anio(anio_gravable)
    uvt = parametros.uvt
    conceptos: List[ParametroAdicional] = []

    for tipo in TipoAdicional:
        codigo = _CODIGO_TOPE.get(tipo)
        tope = parametros.topes_deducciones.get(codigo) if codigo else None
        if tipo == TipoAdicional.DEPENDIENTE:
            limite = parametros.deduccion_dependientes
            conceptos.append(
                ParametroAdicional(
                    tipo=tipo,
                    etiqueta=ETIQUETAS_ADICIONAL[tipo],
                    pide_valor=False,
                    pide_cantidad=True,
                    tope_uvt=limite.tope_uvt,
                    tope_anual_en_pesos=(
                        (limite.tope_uvt * uvt).quantize(Decimal("0.01"))
                        if limite.tope_uvt is not None
                        else None
                    ),
                    cantidad_maxima=parametros.max_dependientes,
                    fuente_legal=limite.fuente_legal,
                    advertencia=_ADVERTENCIA_DEPENDIENTES,
                )
            )
            continue

        conceptos.append(
            ParametroAdicional(
                tipo=tipo,
                etiqueta=ETIQUETAS_ADICIONAL[tipo],
                pide_pais=tipo == TipoAdicional.BIEN_EXTERIOR,
                tope_uvt=tope.tope_uvt if tope else None,
                tope_anual_en_pesos=_tope_en_pesos(tope, uvt),
                es_tope_mensual=bool(tope and tope.es_mensual),
                grupo_tope_compartido=tope.grupo if tope else None,
                fuente_legal=tope.fuente_legal if tope else None,
                advertencia=(
                    _ADVERTENCIA_PORCENTAJE
                    if tope and tope.porcentaje_de_ingresos is not None
                    else None
                ),
            )
        )

    return ParametrosAdicionales(
        anio_gravable=anio_gravable,
        uvt=uvt,
        fuente_uvt=parametros.fuente_uvt,
        conceptos=conceptos,
    )


def _validar_adicional(
    session: Session,
    periodo: PeriodoFiscal,
    datos: DatoAdicionalCrear,
) -> None:
    parametros = _parametros_del_anio(periodo.anio_gravable)
    uvt = parametros.uvt

    if datos.tipo == TipoAdicional.DEPENDIENTE:
        if not datos.cantidad:
            raise TopeAdicionalExcedidoError(
                "Indique a cuántos dependientes corresponde el soporte"
            )
        ya_registrados = sum(
            (d.cantidad or 0)
            for d in session.exec(
                select(DatoAdicional).where(
                    DatoAdicional.periodo_fiscal_id == periodo.id,
                    DatoAdicional.tipo == TipoAdicional.DEPENDIENTE,
                )
            ).all()
        )
        maximo = parametros.max_dependientes
        if ya_registrados + datos.cantidad > maximo:
            raise TopeAdicionalExcedidoError(
                f"Con este registro quedarían {ya_registrados + datos.cantidad} "
                f"dependientes y el máximo del año gravable "
                f"{periodo.anio_gravable} es {maximo}"
            )
        return

    if datos.tipo == TipoAdicional.BIEN_EXTERIOR and not (datos.pais or "").strip():
        raise TopeAdicionalExcedidoError(
            "Indique en qué país está el bien: la declaración de activos del "
            "exterior lo pide por país"
        )

    if datos.valor <= 0:
        raise TopeAdicionalExcedidoError("El valor tiene que ser mayor que cero")

    codigo = _CODIGO_TOPE.get(datos.tipo)
    if codigo is None:
        return
    tope = parametros.topes_deducciones.get(codigo)
    limite = _tope_en_pesos(tope, uvt)
    if limite is None:
        return

    # Los conceptos que comparten tope se validan por la SUMA del grupo: los
    # aportes voluntarios a pensión y el ahorro en AFC no tienen 3.800 UVT
    # cada uno, tienen 3.800 UVT entre los dos.
    tipos_del_grupo = [datos.tipo]
    if tope.grupo:
        tipos_del_grupo = [
            t
            for t, c in _CODIGO_TOPE.items()
            if (parametros.topes_deducciones.get(c).grupo
                if parametros.topes_deducciones.get(c) else None) == tope.grupo
        ]

    acumulado = sum(
        (d.valor for d in session.exec(
            select(DatoAdicional).where(
                DatoAdicional.periodo_fiscal_id == periodo.id,
                DatoAdicional.tipo.in_(tipos_del_grupo),
            )
        ).all()),
        Decimal("0"),
    )
    if acumulado + datos.valor > limite:
        compartido = (
            f" (tope compartido entre {len(tipos_del_grupo)} conceptos)"
            if tope.grupo and len(tipos_del_grupo) > 1
            else ""
        )
        raise TopeAdicionalExcedidoError(
            f"El tope del año gravable {periodo.anio_gravable} para "
            f"«{ETIQUETAS_ADICIONAL[datos.tipo]}» es ${limite:,.0f}{compartido} "
            f"({tope.fuente_legal}). Con este registro la suma quedaría en "
            f"${acumulado + datos.valor:,.0f}."
        )


def agregar_adicional(
    session: Session,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: DatoAdicionalCrear,
    capturado_en_portal: bool = True,
) -> DatoAdicionalLeer:
    """Registra un concepto que la exógena no trae.

    No crea ninguna petición de documento aparte: `gestion` ya deriva de estos
    datos el soporte que hay que pedir (el certificado de medicina prepagada,
    los soportes de los dependientes), así que la lista de documentos se
    actualiza sola y sigue siendo una sola lista.
    """
    periodo = session.get(PeriodoFiscal, periodo_fiscal_id)
    if periodo is None or periodo.contribuyente_id != contribuyente_id:
        raise DatoAdicionalNoEncontradoError(
            f"No existe el periodo fiscal {periodo_fiscal_id} para este contribuyente"
        )
    if periodo.estado == EstadoPeriodo.CERRADO:
        raise PeriodoFiscalCerradoError(
            f"El periodo fiscal {periodo.anio_gravable} está cerrado"
        )

    _validar_adicional(session, periodo, datos)

    adicional = DatoAdicional(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        tipo=datos.tipo,
        descripcion=datos.descripcion.strip(),
        valor=datos.valor,
        cantidad=datos.cantidad,
        pais=(datos.pais or "").strip() or None,
        capturado_en_portal=capturado_en_portal,
    )
    session.add(adicional)
    session.commit()
    session.refresh(adicional)
    return DatoAdicionalLeer(**adicional.model_dump())


def listar_adicionales(
    session: Session, contribuyente_id: int, periodo_fiscal_id: int
) -> List[DatoAdicionalLeer]:
    adicionales = session.exec(
        select(DatoAdicional)
        .where(
            DatoAdicional.contribuyente_id == contribuyente_id,
            DatoAdicional.periodo_fiscal_id == periodo_fiscal_id,
        )
        .order_by(DatoAdicional.tipo, DatoAdicional.id)
    ).all()
    return [DatoAdicionalLeer(**a.model_dump()) for a in adicionales]


def eliminar_adicional(
    session: Session, contribuyente_id: int, periodo_fiscal_id: int, adicional_id: int
) -> None:
    adicional = session.get(DatoAdicional, adicional_id)
    if (
        adicional is None
        or adicional.contribuyente_id != contribuyente_id
        or adicional.periodo_fiscal_id != periodo_fiscal_id
    ):
        raise DatoAdicionalNoEncontradoError(
            f"No existe el dato adicional {adicional_id} en este periodo"
        )
    session.delete(adicional)
    session.commit()


def dependientes_reportados(session: Session, periodo_fiscal_id: int) -> int:
    """Cuántos dependientes soportó el contribuyente en el portal.

    El motor NO lo usa: el número que se declara lo fija el contador en la
    hoja. Esto sirve para mostrarle la diferencia y que decida.
    """
    return sum(
        (d.cantidad or 0)
        for d in session.exec(
            select(DatoAdicional).where(
                DatoAdicional.periodo_fiscal_id == periodo_fiscal_id,
                DatoAdicional.tipo == TipoAdicional.DEPENDIENTE,
            )
        ).all()
    )
