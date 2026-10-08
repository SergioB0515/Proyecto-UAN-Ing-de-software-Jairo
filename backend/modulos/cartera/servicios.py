from typing import Optional

from sqlmodel import Session, select

from ..conciliacion.modelos import EstadoConciliacion
from ..contribuyentes.modelos import PeriodoFiscal
from ..contribuyentes.servicios import listar_contribuyentes
from ..reportes.servicios import evaluar_declaracion
from .modelos import FilaCartera, OrdenCartera, PanelCartera


def _periodo_a_evaluar(
    session: Session, contribuyente_id: int, anio_gravable: Optional[int]
) -> Optional[PeriodoFiscal]:
    """El periodo del año pedido o, si no se pide año, el más reciente."""
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
    """HU-18: solo los contribuyentes del contador autenticado. Por defecto
    ordena por alertas NO_DECLARADO (más urgentes primero) y, a igual número
    de alertas, primero los obligados a declarar."""
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
        fila.alertas_no_declarado = (
            conciliacion[EstadoConciliacion.NO_DECLARADO] if conciliacion is not None else None
        )
        fila.avisos = avisos
        filas.append(fila)

    if orden == OrdenCartera.NOMBRE:
        filas.sort(key=lambda f: f.nombre.lower())
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
        contribuyentes=filas,
    )
