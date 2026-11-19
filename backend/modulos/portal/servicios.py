"""Servicios del portal de carga.

Lo que este módulo garantiza por construcción
---------------------------------------------
El enlace **solo escribe**. Aquí no se importa nada de `liquidacion`, de
`conciliacion` ni de `cartera`, así que no existe camino desde un token hasta
la liquidación del contribuyente: no es una comprobación que haya que
recordar hacer en cada endpoint, es que el código que la expondría no está
disponible en este archivo. Si alguien agrega ese import, la intención del
módulo queda a la vista en el diff.
"""

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import BinaryIO, Dict, List, Optional, Tuple

from sqlmodel import Session, select

from core.excepciones import (
    AnioGravableNoSoportadoError,
    DatoAdicionalNoEncontradoError,
    EnlaceCargaExpiradoError,
    EnlaceCargaNoEncontradoError,
    EnlaceCargaRevocadoError,
    PeriodoFiscalCerradoError,
    PoliticaNoAceptadaError,
    RequerimientoNoEncontradoError,
    TopeAdicionalExcedidoError,
    VersionPoliticaDesconocidaError,
)

from ..adjuntos.modelos import Adjunto, CategoriaAdjunto, TipoEntidadAdjunto
from ..adjuntos.servicios import adjuntar_archivo
from ..contadores.modelos import Contador
from ..contribuyentes.modelos import Contribuyente, EstadoPeriodo, PeriodoFiscal
from ..contribuyentes.servicios import obtener_contribuyente, obtener_periodo_fiscal
from ..exogena.modelos import RegistroExogena, ReporteExogena
from ..exogena.servicios import importar_reporte_exogena
from ..parametros.tablas_oficiales import ANIOS_SOPORTADOS, PARAMETROS_POR_ANIO
from . import lenguaje_comun, politica
from .modelos import (
    AceptarPolitica,
    ArchivoRequerimiento,
    AutorizacionLeer,
    AutorizacionTratamiento,
    DatoAdicional,
    DatoAdicionalCrear,
    DatoAdicionalLeer,
    EnlaceCarga,
    EnlaceCargaCreado,
    EnlaceCargaCrear,
    EnlaceCargaLeer,
    EstadoRequerimiento,
    OrigenRequerimiento,
    ParametroAdicional,
    ParametrosAdicionales,
    PoliticaLeer,
    RequerimientoActualizar,
    RequerimientoDocumento,
    RequerimientoLeer,
    ResumenRequerimientos,
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


def sesion_portal(session: Session, enlace: EnlaceCarga) -> SesionPortal:
    contribuyente = session.get(Contribuyente, enlace.contribuyente_id)
    periodo = session.get(PeriodoFiscal, enlace.periodo_fiscal_id)
    contador = session.get(Contador, enlace.contador_id)
    autorizacion = _autorizacion_vigente(session, enlace)

    reporte = session.exec(
        select(ReporteExogena)
        .where(ReporteExogena.periodo_fiscal_id == enlace.periodo_fiscal_id)
        .order_by(ReporteExogena.version.desc(), ReporteExogena.id.desc())
    ).first()

    requerimientos = listar_requerimientos(
        session, enlace.contribuyente_id, enlace.periodo_fiscal_id
    )
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
        requerimientos=requerimientos,
        adicionales=listar_adicionales(
            session, enlace.contribuyente_id, enlace.periodo_fiscal_id
        ),
        resumen=resumir(requerimientos),
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
    creados, actualizados, sin_reconocer = sincronizar_requerimientos(
        session, reporte
    )
    return ResultadoCargaExogena(
        reporte_exogena_id=reporte.id,
        version=reporte.version,
        fecha_corte=reporte.fecha_corte,
        cantidad_registros=importado.cantidad_registros,
        requerimientos_creados=creados,
        requerimientos_actualizados=actualizados,
        sin_reconocer=sin_reconocer,
        errores_en_filas=len(importado.errores),
    )


# ---------------------------------------------------------------------------
# Requerimientos
# ---------------------------------------------------------------------------


def sincronizar_requerimientos(
    session: Session, reporte: ReporteExogena
) -> Tuple[int, int, int]:
    """Traduce cada fila del reporte a un requerimiento, sin perder progreso.

    Cada fila del archivo produce un requerimiento. Ninguna se descarta: las
    que la aplicación no sabe clasificar entran con `concepto_reconocido` en
    falso para que el contador las resuelva.

    Si el requerimiento de esa fila ya existía (porque el contribuyente volvió
    a cargar el archivo con una fecha de corte más nueva), se actualiza el
    texto y el valor pero **se conservan el estado, el valor informado, la
    nota y los archivos**: son trabajo del contribuyente, no datos del
    archivo.
    """
    registros = session.exec(
        select(RegistroExogena)
        .where(RegistroExogena.reporte_exogena_id == reporte.id)
        .order_by(RegistroExogena.id)
    ).all()

    existentes: Dict[int, RequerimientoDocumento] = {
        r.referencia: r
        for r in session.exec(
            select(RequerimientoDocumento).where(
                RequerimientoDocumento.periodo_fiscal_id == reporte.periodo_fiscal_id,
                RequerimientoDocumento.origen == OrigenRequerimiento.EXOGENA,
            )
        ).all()
    }

    # Los requerimientos de una versión anterior del archivo se identifican
    # por el registro que los originó, y los registros son nuevos en cada
    # importación. Para no duplicarlos se reconcilia por la huella de la fila
    # (tercero + concepto + detalle), que sí es estable entre versiones.
    por_huella: Dict[str, RequerimientoDocumento] = {}
    for requerimiento in existentes.values():
        por_huella.setdefault(_huella(requerimiento), requerimiento)

    creados = actualizados = sin_reconocer = 0

    for registro in registros:
        peticion = lenguaje_comun.traducir(
            registro.detalle,
            registro.nombre_reportante,
            es_auto_reportado=registro.es_auto_reportado,
            es_dian=registro.es_dian,
        )
        if not peticion.concepto_reconocido:
            sin_reconocer += 1

        huella = _huella_de_registro(registro)
        requerimiento = por_huella.pop(huella, None)

        if requerimiento is None:
            requerimiento = RequerimientoDocumento(
                contribuyente_id=reporte.contribuyente_id,
                periodo_fiscal_id=reporte.periodo_fiscal_id,
                origen=OrigenRequerimiento.EXOGENA,
                referencia=registro.id,
            )
            creados += 1
        else:
            requerimiento.referencia = registro.id
            actualizados += 1

        requerimiento.reporte_exogena_id = reporte.id
        requerimiento.titulo = peticion.titulo[:300]
        requerimiento.explicacion = peticion.explicacion[:1000]
        requerimiento.nit_reportante = registro.nit_reportante
        requerimiento.nombre_reportante = registro.nombre_reportante
        requerimiento.concepto_code = registro.concepto_code
        requerimiento.detalle_original = (registro.detalle or "")[:500]
        requerimiento.valor_exogena = registro.valor
        requerimiento.categoria_sugerida = peticion.categoria_sugerida
        requerimiento.concepto_reconocido = peticion.concepto_reconocido
        requerimiento.motivo_revision = peticion.motivo_revision
        requerimiento.requiere_soporte = peticion.requiere_soporte
        requerimiento.actualizado_en = _ahora()
        session.add(requerimiento)

    # Lo que quedó sin pareja venía de una versión anterior del archivo y ya
    # no figura en la exógena. No se borra: puede tener archivos cargados y
    # que un tercero retire un reporte es justo lo que el contador necesita
    # ver. Se marca apuntando al reporte nuevo con un aviso.
    for huerfano in por_huella.values():
        huerfano.concepto_reconocido = False
        huerfano.motivo_revision = (
            "Esta fila ya no aparece en la versión más reciente de la exógena. "
            "El tercero pudo corregir o retirar el reporte: revísela antes de "
            "usarla."
        )
        huerfano.actualizado_en = _ahora()
        session.add(huerfano)

    session.commit()
    return creados, actualizados, sin_reconocer


def _huella(requerimiento: RequerimientoDocumento) -> str:
    return "|".join(
        [
            requerimiento.nit_reportante or "",
            requerimiento.concepto_code or "",
            (requerimiento.detalle_original or "").strip().lower(),
        ]
    )


def _huella_de_registro(registro: RegistroExogena) -> str:
    return "|".join(
        [
            registro.nit_reportante or "",
            registro.concepto_code or "",
            (registro.detalle or "").strip().lower(),
        ]
    )


def _archivos_por_requerimiento(
    session: Session, ids: List[int]
) -> Dict[int, List[ArchivoRequerimiento]]:
    if not ids:
        return {}
    adjuntos = session.exec(
        select(Adjunto)
        .where(
            Adjunto.entidad_tipo == TipoEntidadAdjunto.REQUERIMIENTO,
            Adjunto.entidad_id.in_(ids),
        )
        .order_by(Adjunto.id)
    ).all()
    salida: Dict[int, List[ArchivoRequerimiento]] = {}
    for adjunto in adjuntos:
        salida.setdefault(adjunto.entidad_id, []).append(
            ArchivoRequerimiento(
                id=adjunto.id,
                nombre_original=adjunto.nombre_original,
                tamano_bytes=adjunto.tamano_bytes,
                creado_en=adjunto.creado_en,
            )
        )
    return salida


def _resuelto(requerimiento: RequerimientoDocumento, tiene_archivos: bool) -> bool:
    """Cuándo un requerimiento deja de estar en la lista de lo que falta.

    `NO_ENTIENDO` NO resuelve: es exactamente lo contrario, es el
    contribuyente pidiendo ayuda. Queda pendiente, pero del lado del contador.
    """
    if not requerimiento.requiere_soporte:
        return True
    if requerimiento.estado in (
        EstadoRequerimiento.NO_APLICA,
        EstadoRequerimiento.NO_LO_TENGO,
    ):
        return True
    return tiene_archivos


def _a_lectura_requerimiento(
    requerimiento: RequerimientoDocumento, archivos: List[ArchivoRequerimiento]
) -> RequerimientoLeer:
    return RequerimientoLeer(
        **requerimiento.model_dump(
            exclude={"referencia", "reporte_exogena_id"}
        ),
        archivos=archivos,
        resuelto=_resuelto(requerimiento, bool(archivos)),
    )


def listar_requerimientos(
    session: Session, contribuyente_id: int, periodo_fiscal_id: int
) -> List[RequerimientoLeer]:
    requerimientos = session.exec(
        select(RequerimientoDocumento)
        .where(
            RequerimientoDocumento.contribuyente_id == contribuyente_id,
            RequerimientoDocumento.periodo_fiscal_id == periodo_fiscal_id,
        )
        .order_by(
            RequerimientoDocumento.requiere_soporte.desc(),
            RequerimientoDocumento.id,
        )
    ).all()
    archivos = _archivos_por_requerimiento(session, [r.id for r in requerimientos])
    return [
        _a_lectura_requerimiento(r, archivos.get(r.id, [])) for r in requerimientos
    ]


def obtener_requerimiento(
    session: Session, contribuyente_id: int, periodo_fiscal_id: int, requerimiento_id: int
) -> RequerimientoDocumento:
    requerimiento = session.get(RequerimientoDocumento, requerimiento_id)
    if (
        requerimiento is None
        or requerimiento.contribuyente_id != contribuyente_id
        or requerimiento.periodo_fiscal_id != periodo_fiscal_id
    ):
        raise RequerimientoNoEncontradoError(
            f"No existe el requerimiento {requerimiento_id} en este periodo"
        )
    return requerimiento


def actualizar_requerimiento(
    session: Session,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    requerimiento_id: int,
    cambios: RequerimientoActualizar,
) -> RequerimientoLeer:
    requerimiento = obtener_requerimiento(
        session, contribuyente_id, periodo_fiscal_id, requerimiento_id
    )
    requerimiento.estado = cambios.estado
    requerimiento.valor_informado = cambios.valor_informado
    requerimiento.nota_contribuyente = (cambios.nota_contribuyente or "").strip() or None
    requerimiento.actualizado_en = _ahora()
    # Si el contribuyente volvió a tocar el ítem, lo que el contador había
    # revisado ya no corresponde a este estado.
    requerimiento.revisado_por_contador = False
    session.add(requerimiento)
    session.commit()
    session.refresh(requerimiento)
    archivos = _archivos_por_requerimiento(session, [requerimiento.id])
    return _a_lectura_requerimiento(requerimiento, archivos.get(requerimiento.id, []))


def marcar_revisado(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    requerimiento_id: int,
    revisado: bool = True,
) -> RequerimientoLeer:
    obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    requerimiento = obtener_requerimiento(
        session, contribuyente_id, periodo_fiscal_id, requerimiento_id
    )
    requerimiento.revisado_por_contador = revisado
    session.add(requerimiento)
    session.commit()
    session.refresh(requerimiento)
    archivos = _archivos_por_requerimiento(session, [requerimiento.id])
    return _a_lectura_requerimiento(requerimiento, archivos.get(requerimiento.id, []))


def adjuntar_a_requerimiento(
    session: Session,
    enlace: EnlaceCarga,
    requerimiento_id: int,
    flujo: BinaryIO,
    nombre: Optional[str],
    descripcion: Optional[str] = None,
):
    """Sube un soporte y lo deja atado a su requerimiento.

    El archivo nunca queda suelto en «documentos generales»: el tipo de
    entidad es el requerimiento, así que el contador abre el ítem y ve el
    papel que lo respalda sin tener que adivinar a qué correspondía.
    """
    exigir_politica_aceptada(session, enlace)
    requerimiento = obtener_requerimiento(
        session, enlace.contribuyente_id, enlace.periodo_fiscal_id, requerimiento_id
    )
    categoria = CategoriaAdjunto.OTRO
    try:
        categoria = CategoriaAdjunto(requerimiento.categoria_sugerida)
    except ValueError:
        pass
    return adjuntar_archivo(
        session,
        enlace.contador_id,
        enlace.contribuyente_id,
        TipoEntidadAdjunto.REQUERIMIENTO,
        requerimiento.id,
        flujo,
        nombre,
        categoria,
        descripcion,
    )


def resumir(requerimientos: List[RequerimientoLeer]) -> ResumenRequerimientos:
    resumen = ResumenRequerimientos()
    for requerimiento in requerimientos:
        if not requerimiento.concepto_reconocido and not requerimiento.revisado_por_contador:
            resumen.sin_reconocer += 1
        if not requerimiento.requiere_soporte:
            continue
        resumen.total += 1
        if requerimiento.archivos:
            resumen.con_soporte += 1
        if requerimiento.estado == EstadoRequerimiento.NO_APLICA:
            resumen.no_aplica += 1
        elif requerimiento.estado == EstadoRequerimiento.NO_LO_TENGO:
            resumen.no_lo_tengo += 1
        elif requerimiento.estado == EstadoRequerimiento.NO_ENTIENDO:
            resumen.no_entiendo += 1
        elif not requerimiento.archivos:
            resumen.pendientes += 1
    return resumen


def resumen_del_periodo(
    session: Session, contribuyente_id: int, periodo_fiscal_id: int
) -> ResumenRequerimientos:
    return resumir(listar_requerimientos(session, contribuyente_id, periodo_fiscal_id))


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

_ETIQUETAS: Dict[TipoAdicional, str] = {
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
                    etiqueta=_ETIQUETAS[tipo],
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
                etiqueta=_ETIQUETAS[tipo],
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
            if (parametros.topes_deducciones.get(c).grupo if parametros.topes_deducciones.get(c) else None)
            == tope.grupo
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
            f"«{_ETIQUETAS[datos.tipo]}» es ${limite:,.0f}{compartido} "
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
    session.flush()

    # Cada adicional pide su propio soporte, igual que una fila de la
    # exógena: entra a la misma lista de requerimientos para que no haya dos
    # bandejas distintas de «lo que falta».
    requerimiento = RequerimientoDocumento(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        origen=OrigenRequerimiento.ADICIONAL,
        referencia=adicional.id,
        titulo=f"{_ETIQUETAS[datos.tipo]}: {adicional.descripcion}",
        explicacion=(
            "Esto no lo reporta nadie a la DIAN, así que el soporte tiene que "
            "salir de usted. Cargue el certificado, el recibo o el documento "
            "que lo respalde."
        ),
        detalle_original=f"{datos.tipo.value} — {adicional.descripcion}"[:500],
        valor_exogena=None,
        categoria_sugerida=(
            lenguaje_comun.CERTIFICADO
            if datos.tipo in _CODIGO_TOPE
            else lenguaje_comun.OTRO
        ),
        concepto_reconocido=True,
        requiere_soporte=True,
    )
    session.add(requerimiento)
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
    requerimiento = session.exec(
        select(RequerimientoDocumento).where(
            RequerimientoDocumento.periodo_fiscal_id == periodo_fiscal_id,
            RequerimientoDocumento.origen == OrigenRequerimiento.ADICIONAL,
            RequerimientoDocumento.referencia == adicional_id,
        )
    ).first()
    if requerimiento is not None:
        archivos = _archivos_por_requerimiento(session, [requerimiento.id])
        if archivos:
            raise TopeAdicionalExcedidoError(
                "Este concepto ya tiene soportes cargados. Elimine primero los "
                "archivos: borrarlos en silencio dejaría documentos sin dueño."
            )
        session.delete(requerimiento)
    session.delete(adicional)
    session.commit()


def dependientes_reportados(
    session: Session, periodo_fiscal_id: int
) -> int:
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
