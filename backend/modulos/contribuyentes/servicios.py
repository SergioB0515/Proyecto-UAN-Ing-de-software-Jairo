from typing import List, Optional

from sqlmodel import Session, select

from core.excepciones import (
    ActivoDeCierreError,
    ActivoNoEncontradoError,
    ContribuyenteConDatosError,
    ContribuyenteNoEncontradoError,
    FuenteIngresoNoEncontradaError,
    PeriodoFiscalCerradoError,
    PeriodoFiscalDuplicadoError,
    PeriodoFiscalNoEncontradoError,
)

from .modelos import (
    Activo,
    ActivoActualizar,
    ActivoCrear,
    Contribuyente,
    ContribuyenteActualizar,
    ContribuyenteCrear,
    EstadoPeriodo,
    FuenteIngreso,
    FuenteIngresoActualizar,
    FuenteIngresoCrear,
    PeriodoFiscal,
    PeriodoFiscalCrear,
    TipoActivo,
    TipoContribuyente,
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


def _tiene_inventario(session: Session, contribuyente_id: int) -> bool:
    """¿Tiene categorías, productos, proveedores o documentos soporte?
    Import local: los módulos de inventario importan este módulo."""
    from ..inventario.modelos import Categoria, Producto
    from ..movimientos.modelos import DocumentoSoporte, Proveedor

    return any(
        session.exec(select(modelo.id).where(modelo.contribuyente_id == contribuyente_id)).first()
        is not None
        for modelo in (Categoria, Producto, Proveedor, DocumentoSoporte)
    )


def actualizar_contribuyente(
    session: Session, contador_id: int, contribuyente_id: int, cambios: ContribuyenteActualizar
) -> Contribuyente:
    """Corrige los datos del contribuyente. No se permite pasar a ASALARIADO
    uno que ya tiene inventario: ese inventario dejaría de verse y de
    cerrarse."""
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    datos = cambios.model_dump(exclude_unset=True)
    if (
        datos.get("tipo_contribuyente") == TipoContribuyente.ASALARIADO
        and contribuyente.tipo_contribuyente != TipoContribuyente.ASALARIADO
        and _tiene_inventario(session, contribuyente_id)
    ):
        raise ContribuyenteConDatosError(
            "No se puede cambiar a ASALARIADO: el contribuyente ya tiene inventario registrado"
        )
    for campo, valor in datos.items():
        if valor is not None:  # nombre, rut y tipo no admiten null
            setattr(contribuyente, campo, valor)
    session.add(contribuyente)
    session.commit()
    session.refresh(contribuyente)
    return contribuyente


def eliminar_contribuyente(session: Session, contador_id: int, contribuyente_id: int) -> None:
    """Solo para corregir un registro hecho por error: se rechaza si ya tiene
    periodos fiscales (y con ellos activos, ingresos, exógena o cierres) o
    inventario. Borrar en cascada la información tributaria de un cliente
    con un clic es demasiado riesgoso."""
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    tiene_periodos = (
        session.exec(
            select(PeriodoFiscal.id).where(PeriodoFiscal.contribuyente_id == contribuyente_id)
        ).first()
        is not None
    )
    if tiene_periodos or _tiene_inventario(session, contribuyente_id):
        raise ContribuyenteConDatosError(
            "Solo se puede eliminar un contribuyente sin años gravables ni inventario registrados"
        )
    session.delete(contribuyente)
    session.commit()


def _periodo_abierto_para_registro(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> PeriodoFiscal:
    """Un activo o una fuente de ingreso solo se registra en un periodo del
    mismo contribuyente que siga ABIERTO: un periodo cerrado ya quedó
    consolidado (HU-15)."""
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    if periodo.estado == EstadoPeriodo.CERRADO:
        raise PeriodoFiscalCerradoError(
            f"El periodo {periodo.anio_gravable} está cerrado: reábrelo para "
            "registrar cambios"
        )
    return periodo


def agregar_activo(
    session: Session, contador_id: int, contribuyente_id: int, datos: ActivoCrear
) -> Activo:
    """HU-04. Valida pertenencia al contador y que el periodo esté abierto."""
    _periodo_abierto_para_registro(
        session, contador_id, contribuyente_id, datos.periodo_fiscal_id
    )
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
    """HU-03. Valida pertenencia al contador y que el periodo esté abierto."""
    _periodo_abierto_para_registro(
        session, contador_id, contribuyente_id, datos.periodo_fiscal_id
    )
    fuente = FuenteIngreso(**datos.model_dump(), contribuyente_id=contribuyente_id)
    session.add(fuente)
    session.commit()
    session.refresh(fuente)
    return fuente


def _normalizar_vinculos(datos: dict) -> dict:
    """Un vínculo DIAN vacío se guarda como null."""
    for campo in ("vinculo_codigo_concepto", "vinculo_palabra_clave"):
        if campo in datos and isinstance(datos[campo], str):
            datos[campo] = datos[campo].strip() or None
    return datos


def _activo_editable(
    session: Session, contador_id: int, contribuyente_id: int, activo_id: int
) -> Activo:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    activo = session.get(Activo, activo_id)
    if activo is None or activo.contribuyente_id != contribuyente_id:
        raise ActivoNoEncontradoError(
            f"No existe el activo {activo_id} para el contribuyente {contribuyente_id}"
        )
    if activo.tipo == TipoActivo.INVENTARIO:
        raise ActivoDeCierreError(
            "El inventario lo registra el cierre del periodo: para cambiarlo, reabre el año"
        )
    _periodo_abierto_para_registro(session, contador_id, contribuyente_id, activo.periodo_fiscal_id)
    return activo


def actualizar_activo(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    activo_id: int,
    cambios: ActivoActualizar,
) -> Activo:
    """Corrige un activo de un periodo abierto. Los campos obligatorios
    enviados como null se ignoran; los vínculos DIAN en null se borran."""
    activo = _activo_editable(session, contador_id, contribuyente_id, activo_id)
    for campo, valor in _normalizar_vinculos(cambios.model_dump(exclude_unset=True)).items():
        if valor is not None or campo.startswith("vinculo_"):
            setattr(activo, campo, valor)
    session.add(activo)
    session.commit()
    session.refresh(activo)
    return activo


def eliminar_activo(
    session: Session, contador_id: int, contribuyente_id: int, activo_id: int
) -> None:
    activo = _activo_editable(session, contador_id, contribuyente_id, activo_id)
    session.delete(activo)
    session.commit()


def _fuente_editable(
    session: Session, contador_id: int, contribuyente_id: int, fuente_id: int
) -> FuenteIngreso:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    fuente = session.get(FuenteIngreso, fuente_id)
    if fuente is None or fuente.contribuyente_id != contribuyente_id:
        raise FuenteIngresoNoEncontradaError(
            f"No existe la fuente de ingreso {fuente_id} para el contribuyente {contribuyente_id}"
        )
    _periodo_abierto_para_registro(session, contador_id, contribuyente_id, fuente.periodo_fiscal_id)
    return fuente


def actualizar_fuente_ingreso(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    fuente_id: int,
    cambios: FuenteIngresoActualizar,
) -> FuenteIngreso:
    fuente = _fuente_editable(session, contador_id, contribuyente_id, fuente_id)
    for campo, valor in _normalizar_vinculos(cambios.model_dump(exclude_unset=True)).items():
        if valor is not None or campo.startswith("vinculo_"):
            setattr(fuente, campo, valor)
    session.add(fuente)
    session.commit()
    session.refresh(fuente)
    return fuente


def eliminar_fuente_ingreso(
    session: Session, contador_id: int, contribuyente_id: int, fuente_id: int
) -> None:
    fuente = _fuente_editable(session, contador_id, contribuyente_id, fuente_id)
    session.delete(fuente)
    session.commit()


def listar_activos(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: Optional[int] = None,
) -> List[Activo]:
    """Todos los activos del contribuyente, o solo los de un periodo."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    consulta = select(Activo).where(Activo.contribuyente_id == contribuyente_id)
    if periodo_fiscal_id is not None:
        obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
        consulta = consulta.where(Activo.periodo_fiscal_id == periodo_fiscal_id)
    return list(session.exec(consulta.order_by(Activo.id)).all())


def listar_fuentes_ingreso(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: Optional[int] = None,
) -> List[FuenteIngreso]:
    """Todas las fuentes de ingreso del contribuyente, o solo las de un
    periodo."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    consulta = select(FuenteIngreso).where(
        FuenteIngreso.contribuyente_id == contribuyente_id
    )
    if periodo_fiscal_id is not None:
        obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
        consulta = consulta.where(FuenteIngreso.periodo_fiscal_id == periodo_fiscal_id)
    return list(session.exec(consulta.order_by(FuenteIngreso.id)).all())


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
            select(PeriodoFiscal)
            .where(PeriodoFiscal.contribuyente_id == contribuyente_id)
            .order_by(PeriodoFiscal.anio_gravable)
        ).all()
    )


def periodo_mas_reciente(
    session: Session, contador_id: int, contribuyente_id: int
) -> Optional[PeriodoFiscal]:
    """El periodo de mayor año gravable, o None si no tiene ninguno."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    return session.exec(
        select(PeriodoFiscal)
        .where(PeriodoFiscal.contribuyente_id == contribuyente_id)
        .order_by(PeriodoFiscal.anio_gravable.desc())
    ).first()


def calcular_patrimonio_liquido(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> float:
    """HU-04: suma de los activos del periodo. El Activo INVENTARIO que crea
    el cierre (Incremento 5) queda en el periodo cerrado, así que cada año
    cuenta solo su propio inventario final."""
    return sum(
        activo.valor
        for activo in listar_activos(session, contador_id, contribuyente_id, periodo_fiscal_id)
    )
