from datetime import date
from typing import Optional

from sqlmodel import Session, select

from ..conciliacion.modelos import EstadoConciliacion
from ..contribuyentes.modelos import PeriodoFiscal
from ..contribuyentes.servicios import listar_contribuyentes
from ..exogena.modelos import ReporteExogena
from ..parametros.modelos import EstadoVencimiento
from ..parametros.servicios import calcular_vencimiento
from ..portal.modelos import AutorizacionTratamiento, EnlaceCarga
from ..portal.servicios import esta_vigente, resumen_del_periodo
from ..reportes.servicios import evaluar_declaracion
from .modelos import FilaCartera, OrdenCartera, PanelCartera


def _periodo_a_evaluar(
    session: Session, contribuyente_id: int, anio_gravable: Optional[int]
) -> Optional[PeriodoFiscal]:
    consulta = select(PeriodoFiscal).where(PeriodoFiscal.contribuyente_id == contribuyente_id)
    if anio_gravable is not None:
        consulta = consulta.where(PeriodoFiscal.anio_gravable == anio_gravable)
    return session.exec(consulta.order_by(PeriodoFiscal.anio_gravable.desc())).first()


def panel_cartera(
    session: Session,
    contador_id: int,
    anio_gravable: Optional[int] = None,
    orden: OrdenCartera = OrdenCartera.ALERTAS,
) -> PanelCartera:
    filas = []
    for contribuyente in listar_contribuyentes(session, contador_id):
        fila = FilaCartera(
            contribuyente_id=contribuyente.id,
            nombre=contribuyente.nombre,
            rut=contribuyente.rut,
            tipo_contribuyente=contribuyente.tipo_contribuyente,
        )
        periodo = _periodo_a_evaluar(session, contribuyente.id, anio_gravable)
        if periodo is None:
            fila.avisos = ["No tiene periodo fiscal" + (f" para {anio_gravable}." if anio_gravable else ".")]
            filas.append(fila)
            continue

        obligacion, conciliacion, avisos = evaluar_declaracion(
            session, contador_id, contribuyente.id, periodo.id
        )
        fila.periodo_fiscal_id = periodo.id
        fila.anio_gravable = periodo.anio_gravable
        fila.estado_periodo = periodo.estado
        fila.obligado = obligacion.obligado if obligacion is not None else None
        fila.vencimiento = calcular_vencimiento(
            session,
            contribuyente.rut,
            periodo.anio_gravable,
            periodo.fecha_vencimiento_manual,
            periodo.fecha_presentacion,
        )
        fila.alertas_no_declarado = (
            conciliacion[EstadoConciliacion.NO_DECLARADO] if conciliacion is not None else None
        )
        from ..gestion.servicios import proceso_resumido

        proceso = proceso_resumido(session, contribuyente.id, periodo)
        fila.etapa_actual = proceso.etapa_actual
        fila.etapa_nombre = next(
            (e.accion for e in proceso.etapas if e.clave == proceso.etapa_actual),
            "Terminada",
        )
        fila.etapas_hechas, fila.etapas_total = proceso.hechas, proceso.total
        fila.documentos_pendientes = proceso.documentos_pendientes
        # Los avisos del proceso, más los de la recolección de soportes. Son
        # cuentas distintas: `documentos_pendientes` son las etapas del proceso
        # de la temporada, y `requerimientos` son los papeles que el
        # contribuyente todavía no ha cargado por el enlace.
        fila.avisos = list(avisos) + _completar_recoleccion(
            session, fila, contribuyente.id, periodo.id
        )
        filas.append(fila)

    if orden == OrdenCartera.PENDIENTES:
        filas.sort(
            key=lambda f: (
                -(f.requerimientos.no_entiendo),
                -(f.requerimientos.pendientes),
                -(f.requerimientos.sin_reconocer),
                f.nombre.lower(),
            )
        )
    elif orden == OrdenCartera.NOMBRE:
        filas.sort(key=lambda f: f.nombre.lower())
    elif orden == OrdenCartera.VENCIMIENTO:
        def clave(f):
            v = f.vencimiento
            if v is None or v.estado == EstadoVencimiento.SIN_FECHA:
                return (1, date.max, f.nombre.lower())
            if v.estado == EstadoVencimiento.PRESENTADA:
                return (2, date.max, f.nombre.lower())
            return (0, v.fecha, f.nombre.lower())

        filas.sort(key=clave)
    else:
        filas.sort(
            key=lambda f: (
                f.alertas_no_declarado is None,
                -(f.alertas_no_declarado or 0),
                f.obligado is not True,
                f.nombre.lower(),
            )
        )

    return PanelCartera(
        anio_gravable=anio_gravable,
        total_contribuyentes=len(filas),
        total_obligados=sum(1 for f in filas if f.obligado),
        total_alertas=sum(f.alertas_no_declarado or 0 for f in filas),
        total_vencidas=sum(
            1 for f in filas if f.vencimiento and f.vencimiento.estado == EstadoVencimiento.VENCIDA
        ),
        total_proximas=sum(
            1 for f in filas if f.vencimiento and f.vencimiento.estado == EstadoVencimiento.PROXIMA
        ),
        total_soportes_pendientes=sum(f.requerimientos.pendientes for f in filas),
        total_no_entiendo=sum(f.requerimientos.no_entiendo for f in filas),
        total_conceptos_sin_reconocer=sum(f.requerimientos.sin_reconocer for f in filas),
        total_sin_enlace=sum(
            1 for f in filas if f.periodo_fiscal_id is not None and not f.enlace_vigente
        ),
        contribuyentes=filas,
    )


def _completar_recoleccion(
    session: Session, fila: FilaCartera, contribuyente_id: int, periodo_fiscal_id: int
) -> list:
    """Llena el estado de la recolección y devuelve los avisos que genera.

    Esta es la parte del panel que responde «a quién le falta qué»: sin ella
    hay que entrar a cada ficha para saber si el cliente ya mandó los papeles,
    que es exactamente el trabajo que el panel existe para ahorrar.
    """
    reporte = session.exec(
        select(ReporteExogena)
        .where(ReporteExogena.periodo_fiscal_id == periodo_fiscal_id)
        .order_by(ReporteExogena.version.desc(), ReporteExogena.id.desc())
    ).first()
    fila.exogena_cargada = reporte is not None
    if reporte is not None:
        fila.fecha_corte_exogena = reporte.fecha_corte
        fila.version_exogena = reporte.version

    enlace = session.exec(
        select(EnlaceCarga)
        .where(
            EnlaceCarga.contribuyente_id == contribuyente_id,
            EnlaceCarga.periodo_fiscal_id == periodo_fiscal_id,
        )
        .order_by(EnlaceCarga.id.desc())
    ).first()
    if enlace is not None:
        fila.enlace_vigente = esta_vigente(enlace)
        fila.enlace_ultimo_acceso = (
            enlace.ultimo_acceso_en.date() if enlace.ultimo_acceso_en else None
        )

    fila.politica_aceptada = (
        session.exec(
            select(AutorizacionTratamiento.id).where(
                AutorizacionTratamiento.contribuyente_id == contribuyente_id
            )
        ).first()
        is not None
    )

    fila.requerimientos = resumen_del_periodo(
        session, contribuyente_id, periodo_fiscal_id
    )

    avisos = []
    resumen = fila.requerimientos
    if resumen.no_entiendo:
        avisos.append(
            f"{resumen.no_entiendo} ítem(s) marcados «no entiendo»: esperan "
            "explicación suya."
        )
    if resumen.pendientes:
        avisos.append(f"Faltan {resumen.pendientes} soporte(s) por cargar.")
    if resumen.no_lo_tengo:
        avisos.append(
            f"{resumen.no_lo_tengo} soporte(s) que el contribuyente dice no tener."
        )
    if resumen.sin_reconocer:
        avisos.append(
            f"{resumen.sin_reconocer} concepto(s) de la exógena sin clasificar."
        )
    if resumen.total and not fila.enlace_vigente:
        avisos.append("No tiene un enlace de carga vigente.")
    return avisos


_ESTADOS_VENCIMIENTO = {
    EstadoVencimiento.PRESENTADA: "Presentada",
    EstadoVencimiento.VENCIDA: "Vencida",
    EstadoVencimiento.PROXIMA: "Próxima a vencer",
    EstadoVencimiento.PENDIENTE: "Pendiente",
    EstadoVencimiento.SIN_FECHA: "Sin fecha",
}


def exportar_panel(panel: PanelCartera, formato: str, contador_nombre: str):
    from datetime import datetime

    from ..reportes.exportacion import DocumentoReporte, Seccion, a_excel, a_pdf

    filas = []
    for f in panel.contribuyentes:
        v = f.vencimiento
        filas.append([
            f.nombre,
            f.rut,
            f.tipo_contribuyente.value.capitalize(),
            f.anio_gravable,
            f.estado_periodo.value.capitalize() if f.estado_periodo else None,
            f.obligado,
            f.alertas_no_declarado,
            f.fecha_corte_exogena,
            f.requerimientos.pendientes,
            f.requerimientos.no_entiendo,
            f.requerimientos.sin_reconocer,
            "Sí" if f.enlace_vigente else "No",
            v.fecha if v else None,
            _ESTADOS_VENCIMIENTO[v.estado] if v else None,
            v.fecha_presentacion if v else None,
            "; ".join(f.avisos) or None,
        ])
    documento = DocumentoReporte(
        titulo="Panel de cartera",
        encabezado=[
            f"Contador: {contador_nombre}",
            f"Año gravable: {panel.anio_gravable or 'el más reciente de cada contribuyente'}",
            f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ],
        secciones=[
            Seccion(
                "Totales",
                ["Contribuyentes", "Obligados", "Conceptos sin declarar", "Vencidas",
                 "Próximas a vencer", "Soportes pendientes", "«No entiendo»",
                 "Conceptos sin clasificar", "Sin enlace vigente"],
                [[panel.total_contribuyentes, panel.total_obligados, panel.total_alertas,
                  panel.total_vencidas, panel.total_proximas,
                  panel.total_soportes_pendientes, panel.total_no_entiendo,
                  panel.total_conceptos_sin_reconocer, panel.total_sin_enlace]],
            ),
            Seccion(
                "Contribuyentes",
                ["Contribuyente", "NIT", "Tipo", "Año", "Periodo", "¿Obligado?",
                 "Sin declarar", "Corte exógena", "Soportes pendientes",
                 "«No entiendo»", "Sin clasificar", "¿Enlace vigente?",
                 "Vence", "Declaración", "Presentada el", "Avisos"],
                filas,
            ),
        ],
    )
    contenido = a_excel(documento) if formato == "xlsx" else a_pdf(documento)
    nombre = f"cartera_{panel.anio_gravable or 'reciente'}_{datetime.now():%Y%m%d}.{formato}"
    return contenido, nombre
