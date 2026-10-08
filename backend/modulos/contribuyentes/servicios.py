from typing import List

from sqlmodel import Session, select

from core.excepciones import (
    ContribuyenteNoEncontradoError,
    PeriodoFiscalDuplicadoError,
    PeriodoFiscalNoEncontradoError,
)

from .modelos import (
    Activo,
    ActivoCrear,
    Contribuyente,
    ContribuyenteCrear,
    FuenteIngreso,
    FuenteIngresoCrear,
    PeriodoFiscal,
    PeriodoFiscalCrear,
    TipoActivo,
)


def crear_contribuyente(
    session: Session, contador_id: int, datos: ContribuyenteCrear
) -> Contribuyente:
    """HU-02."""
    contribuyente = Contribuyente(**datos.model_dump(), contador_id=contador_id)
    session.add(contribuyente)
    session.commit()
    session.refresh(contribuyente)
    return contribuyente


def listar_contribuyentes(
    session: Session, contador_id: int
) -> List[Contribuyente]:
    """Solo los contribuyentes del contador autenticado — nunca los de
    otro (HU-02, aislamiento por contador)."""
    return list(
        session.exec(
            select(Contribuyente).where(Contribuyente.contador_id == contador_id)
        ).all()
    )


def obtener_contribuyente(
    session: Session, contador_id: int, contribuyente_id: int
) -> Contribuyente:
    """Lanza ContribuyenteNoEncontradoError tanto si el id no existe como
    si existe pero pertenece a otro contador — deliberadamente el mismo
    error en los dos casos, para no revelar por el código de respuesta que
    el contribuyente sí existe pero es ajeno."""
    contribuyente = session.get(Contribuyente, contribuyente_id)
    if contribuyente is None or contribuyente.contador_id != contador_id:
        raise ContribuyenteNoEncontradoError(
            f"No existe el contribuyente {contribuyente_id} para este contador"
        )
    return contribuyente


def agregar_activo(
    session: Session, contador_id: int, contribuyente_id: int, datos: ActivoCrear
) -> Activo:
    """HU-04. Valida pertenencia al contador antes de escribir."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    activo = Activo(**datos.model_dump(), contribuyente_id=contribuyente_id)
    session.add(activo)
    session.commit()
    session.refresh(activo)
    return activo


def agregar_fuente_ingreso(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    datos: FuenteIngresoCrear,
) -> FuenteIngreso:
    """HU-03. Valida pertenencia al contador antes de escribir."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    fuente = FuenteIngreso(**datos.model_dump(), contribuyente_id=contribuyente_id)
    session.add(fuente)
    session.commit()
    session.refresh(fuente)
    return fuente


def listar_activos(
    session: Session, contador_id: int, contribuyente_id: int
) -> List[Activo]:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    return list(
        session.exec(
            select(Activo).where(Activo.contribuyente_id == contribuyente_id)
        ).all()
    )


def listar_fuentes_ingreso(
    session: Session, contador_id: int, contribuyente_id: int
) -> List[FuenteIngreso]:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    return list(
        session.exec(
            select(FuenteIngreso).where(
                FuenteIngreso.contribuyente_id == contribuyente_id
            )
        ).all()
    )


def crear_periodo_fiscal(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    datos: PeriodoFiscalCrear,
) -> PeriodoFiscal:
    """Nuevo en el Incremento 2 — necesario para asociar un ReporteExogena.
    CRUD simple, sin lógica de negocio propia todavía (el cierre de periodo
    es Incremento 5)."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    existente = session.exec(
        select(PeriodoFiscal).where(
            PeriodoFiscal.contribuyente_id == contribuyente_id,
            PeriodoFiscal.anio_gravable == datos.anio_gravable,
        )
    ).first()
    if existente is not None:
        raise PeriodoFiscalDuplicadoError(
            f"El contribuyente {contribuyente_id} ya tiene un periodo fiscal "
            f"para el año gravable {datos.anio_gravable}"
        )

    periodo = PeriodoFiscal(**datos.model_dump(), contribuyente_id=contribuyente_id)
    session.add(periodo)
    session.commit()
    session.refresh(periodo)
    return periodo


def obtener_periodo_fiscal(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> PeriodoFiscal:
    """Valida la pertenencia del contribuyente al contador y del periodo al
    contribuyente. Lanza PeriodoFiscalNoEncontradoError en el segundo caso —
    lo usan exogena, parametros, conciliacion y movimientos."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    periodo = session.get(PeriodoFiscal, periodo_fiscal_id)
    if periodo is None or periodo.contribuyente_id != contribuyente_id:
        raise PeriodoFiscalNoEncontradoError(
            f"No existe el periodo fiscal {periodo_fiscal_id} para el "
            f"contribuyente {contribuyente_id}"
        )
    return periodo


def listar_periodos_fiscales(
    session: Session, contador_id: int, contribuyente_id: int
) -> List[PeriodoFiscal]:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    return list(
        session.exec(
            select(PeriodoFiscal).where(
                PeriodoFiscal.contribuyente_id == contribuyente_id
            )
        ).all()
    )


def activos_vigentes(
    session: Session, contador_id: int, contribuyente_id: int
) -> List[Activo]:
    """Los activos que componen el patrimonio actual. Cada cierre de periodo
    (Incremento 5) agrega un Activo INVENTARIO con el saldo de ese año;
    solo cuenta el más reciente, porque el inventario de un año ya está
    contenido en el saldo inicial del siguiente. Los cierres van en orden de
    año, así que el de mayor id es el del último año cerrado."""
    activos = listar_activos(session, contador_id, contribuyente_id)
    inventarios = [a for a in activos if a.tipo == TipoActivo.INVENTARIO]
    inventario_vigente = max(inventarios, key=lambda a: a.id, default=None)
    return [
        activo
        for activo in activos
        if activo.tipo != TipoActivo.INVENTARIO or activo is inventario_vigente
    ]


def calcular_patrimonio_liquido(
    session: Session, contador_id: int, contribuyente_id: int
) -> float:
    """HU-04: suma de los activos vigentes del contribuyente."""
    return sum(
        activo.valor for activo in activos_vigentes(session, contador_id, contribuyente_id)
    )
