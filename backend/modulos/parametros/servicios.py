"""Lógica de negocio del módulo de parámetros.

`registrar_umbral` y `obtener_umbral_vigente` ya están implementadas (CRUD
simple). `verificar_obligacion_declarar` está sin implementar a propósito
— es la segunda pieza central del Incremento 2, junto con el parseo de
exogena/servicios.py. La firma, el docstring y los tests
(tests/test_parametros.py) ya están definidos.
"""
from typing import List, Optional

from sqlmodel import Session, select

from core.excepciones import UmbralNoConfiguradoError

from ..contribuyentes.servicios import obtener_contribuyente
from .modelos import (
    DetalleCriterio,
    ResultadoObligacion,
    UmbralDeclaracion,
    UmbralDeclaracionCrear,
)


def registrar_umbral(
    session: Session, datos: UmbralDeclaracionCrear
) -> UmbralDeclaracion:
    """Crea o actualiza el umbral de un año gravable (la llave primaria es
    `anio_gravable`, así que registrar de nuevo el mismo año lo
    sobrescribe). Ya implementada."""
    umbral = UmbralDeclaracion(**datos.model_dump())
    umbral = session.merge(umbral)
    session.commit()
    session.refresh(umbral)
    return umbral


def obtener_umbral_vigente(session: Session, anio_gravable: int) -> UmbralDeclaracion:
    """Ya implementada. Lanza UmbralNoConfiguradoError si nadie ha
    registrado el umbral de ese año todavía."""
    umbral = session.get(UmbralDeclaracion, anio_gravable)
    if umbral is None:
        raise UmbralNoConfiguradoError(
            f"No hay UmbralDeclaracion configurado para el año gravable {anio_gravable}"
        )
    return umbral


def listar_umbrales(session: Session) -> List[UmbralDeclaracion]:
    """Ya implementada."""
    return list(session.exec(select(UmbralDeclaracion)).all())


def verificar_obligacion_declarar(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
) -> ResultadoObligacion:
    """Determina si un contribuyente está obligado a declarar renta en un
    periodo fiscal, comparando los Topes de su exógena importada contra el
    UmbralDeclaracion del año correspondiente (HU-07,
    documentacion/03-logica-proyecto.md Proceso 5).

    QUÉ DEBE HACER:

    1. Validar pertenencia: `obtener_contribuyente(session, contador_id,
       contribuyente_id)` (ya importada arriba). Deja propagar
       `ContribuyenteNoEncontradoError` si falla.

    2. Buscar el `PeriodoFiscal` con id `periodo_fiscal_id` (con
       `session.get`). Si no existe o su `contribuyente_id` no coincide
       con `contribuyente_id`, lanza `PeriodoFiscalNoEncontradoError`
       (impórtala de `core.excepciones`). Necesitas su `anio_gravable`
       más adelante.

    3. Buscar el `ReporteExogena` más reciente de ese periodo: filtra por
       `periodo_fiscal_id` y ordena por `fecha_importacion` descendente,
       toma el primero. Si no hay ninguno, lanza
       `ReporteExogenaNoEncontradoError` (de `core.excepciones`) — no se
       puede verificar la obligación sin haber importado la exógena
       primero.

    4. Traer los `TopeExogena` de ese reporte (`where reporte_exogena_id
       == reporte.id`).

    5. Traer el umbral vigente con `obtener_umbral_vigente(session,
       periodo.anio_gravable)` (ya implementada arriba, en este mismo
       archivo) — déjala propagar `UmbralNoConfiguradoError` si no hay
       umbral configurado para ese año.

    6. Para cada uno de los cinco criterios, encontrar su `TopeExogena`
       correspondiente buscando una palabra clave (sin distinguir
       mayúsculas/minúsculas) dentro de `TopeExogena.etiqueta` — NO
       compares la etiqueta completa, porque el texto exacto puede variar
       ligeramente entre archivos:
         - "ingreso"    -> criterio "Ingresos",   umbral = valor_uvt * tope_ingresos_uvt
         - "patrimonio" -> criterio "Patrimonio", umbral = valor_uvt * tope_patrimonio_uvt
         - "consumo"    -> criterio "Consumo TC", umbral = valor_uvt * tope_consumo_tc_uvt
         - "movimiento" -> criterio "Movimiento", umbral = valor_uvt * tope_movimiento_uvt
         - "compra"     -> criterio "Compras",    umbral = valor_uvt * tope_compras_uvt
       Si alguno de los cinco no aparece entre los Topes del reporte,
       trátalo con `valor_reportado=0.0` (no lo excluyas del resultado —
       el contador necesita ver los cinco criterios siempre, aunque
       alguno no haya venido en el archivo).

    7. Por cada criterio, arma un `DetalleCriterio(criterio=...,
       valor_reportado=..., umbral=..., supera_umbral=valor_reportado >=
       umbral)`.

    8. `obligado` es `True` si CUALQUIERA de los cinco `supera_umbral` es
       `True` (basta con superar uno solo).

    9. Devuelve `ResultadoObligacion(contribuyente_id=..., periodo_fiscal_id=...,
       anio_gravable=periodo.anio_gravable, obligado=..., criterios=[...])`
       — el campo `advertencia` ya tiene un valor por defecto en el
       modelo, no hace falta que lo pases.
    """
    raise NotImplementedError
