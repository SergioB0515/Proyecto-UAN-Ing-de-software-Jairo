from datetime import date
from typing import Optional

from sqlmodel import Session, select

from ..conciliacion.modelos import EstadoConciliacion
from ..contribuyentes.modelos import PeriodoFiscal
from ..contribuyentes.servicios import listar_contribuyentes
from ..parametros.modelos import EstadoVencimiento
from ..parametros.servicios import calcular_vencimiento
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
        fila.avisos = avisos
        filas.append(fila)

    if orden == OrdenCartera.NOMBRE:
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
        contribuyentes=filas,
    )


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
                ["Contribuyentes", "Obligados", "Conceptos sin declarar", "Vencidas", "Próximas a vencer"],
                [[panel.total_contribuyentes, panel.total_obligados, panel.total_alertas,
                  panel.total_vencidas, panel.total_proximas]],
            ),
            Seccion(
                "Contribuyentes",
                ["Contribuyente", "NIT", "Tipo", "Año", "Periodo", "¿Obligado?",
                 "Sin declarar", "Vence", "Declaración", "Presentada el", "Avisos"],
                filas,
            ),
        ],
    )
    contenido = a_excel(documento) if formato == "xlsx" else a_pdf(documento)
    nombre = f"cartera_{panel.anio_gravable or 'reciente'}_{datetime.now():%Y%m%d}.{formato}"
    return contenido, nombre
