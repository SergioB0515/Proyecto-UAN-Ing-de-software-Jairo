from typing import List

from sqlmodel import Session, select

from core.excepciones import UmbralNoConfiguradoError

from ..contribuyentes.servicios import obtener_periodo_fiscal
from ..exogena.modelos import TopeExogena
from ..exogena.servicios import obtener_reporte_mas_reciente
from .modelos import (
    DetalleCriterio,
    ResultadoObligacion,
    UmbralDeclaracion,
    UmbralDeclaracionCrear,
)


def registrar_umbral(
    session: Session, datos: UmbralDeclaracionCrear
) -> UmbralDeclaracion:
    """Crea o reemplaza el umbral de un año gravable (el año es la llave)."""
    umbral = UmbralDeclaracion(**datos.model_dump())
    umbral = session.merge(umbral)
    session.commit()
    session.refresh(umbral)
    return umbral


def obtener_umbral_vigente(session: Session, anio_gravable: int) -> UmbralDeclaracion:
    umbral = session.get(UmbralDeclaracion, anio_gravable)
    if umbral is None:
        raise UmbralNoConfiguradoError(
            f"No hay UmbralDeclaracion configurado para el año gravable {anio_gravable}"
        )
    return umbral


def listar_umbrales(session: Session) -> List[UmbralDeclaracion]:
    return list(
        session.exec(
            select(UmbralDeclaracion).order_by(UmbralDeclaracion.anio_gravable)
        ).all()
    )


def verificar_obligacion_declarar(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
) -> ResultadoObligacion:
    """HU-07: compara los Topes del reporte más reciente del periodo contra
    el UmbralDeclaracion de su año gravable. Basta con que un criterio
    alcance su umbral para quedar obligado (Proceso 5)."""
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    reporte = obtener_reporte_mas_reciente(session, periodo_fiscal_id)

    topes = session.exec(
        select(TopeExogena).where(TopeExogena.reporte_exogena_id == reporte.id)
    ).all()

    umbral = obtener_umbral_vigente(session, periodo.anio_gravable)

    definiciones = [
        ("ingreso", "Ingresos", umbral.tope_ingresos_uvt),
        ("patrimonio", "Patrimonio", umbral.tope_patrimonio_uvt),
        ("consumo", "Consumo TC", umbral.tope_consumo_tc_uvt),
        ("movimiento", "Movimiento", umbral.tope_movimiento_uvt),
        ("compra", "Compras", umbral.tope_compras_uvt),
    ]

    criterios = []
    for palabra_clave, nombre, tope_uvt in definiciones:
        tope = next(
            (t for t in topes if palabra_clave in t.etiqueta.lower()), None
        )
        valor_reportado = tope.valor if tope is not None else 0.0
        valor_umbral = umbral.valor_uvt * tope_uvt
        criterios.append(
            DetalleCriterio(
                criterio=nombre,
                valor_reportado=valor_reportado,
                umbral=valor_umbral,
                supera_umbral=valor_reportado >= valor_umbral,
            )
        )

    return ResultadoObligacion(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        anio_gravable=periodo.anio_gravable,
        obligado=any(c.supera_umbral for c in criterios),
        criterios=criterios,
    )
