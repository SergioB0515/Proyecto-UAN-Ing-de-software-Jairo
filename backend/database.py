from typing import Iterator

from datetime import date

from sqlalchemy import Enum as EnumSQL, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from core.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)


def registrar_modelos() -> None:
    from modulos.adjuntos.modelos import Adjunto
    from modulos.auditoria.modelos import EventoAuditoria, IntentoAcceso
    from modulos.conciliacion.modelos import DecisionRenglon
    from modulos.contadores.modelos import Contador
    from modulos.contribuyentes.modelos import (
        Activo,
        Contribuyente,
        FuenteIngreso,
        PeriodoFiscal,
    )
    from modulos.exogena.modelos import (
        ConceptoDian,
        RegistroExogena,
        ReporteExogena,
        TopeExogena,
    )
    from modulos.inventario.modelos import Categoria, Producto
    from modulos.gestion.modelos import (
        DeclaracionPresentada,
        DocumentoSolicitado,
        SeguimientoDeclaracion,
        TasaInteresMoratorio,
    )
    from modulos.liquidacion.modelos import (
        ClasificacionIngreso,
        DatosDepreciacion,
        DeduccionSolicitada,
        HojaLiquidacion,
        PagoEfectivo,
        PerdidaFiscal,
        VentaInmueble,
    )
    from modulos.movimientos.modelos import (
        DocumentoSoporte,
        Movimiento,
        Proveedor,
    )
    from modulos.parametros.modelos import PlazoDeclaracion, UmbralDeclaracion
    from modulos.portal.modelos import (
        AutorizacionTratamiento,
        DatoAdicional,
        EnlaceCarga,
    )
    from modulos.reportes.modelos import CierrePeriodo


def _migrar_periodo_en_activos_y_fuentes(motor) -> None:
    inspector = inspect(motor)
    tablas = set(inspector.get_table_names())
    pendientes = [
        t
        for t in ("activos", "fuentes_ingreso")
        if t in tablas
        and "periodo_fiscal_id" not in {c["name"] for c in inspector.get_columns(t)}
    ]
    if not pendientes:
        return

    anio_por_defecto = date.today().year - 1
    with motor.begin() as conexion:
        for tabla in pendientes:
            conexion.execute(text(f"ALTER TABLE {tabla} ADD COLUMN periodo_fiscal_id INTEGER"))

            sin_periodo = conexion.execute(
                text(
                    f"SELECT DISTINCT t.contribuyente_id FROM {tabla} t "
                    "WHERE NOT EXISTS (SELECT 1 FROM periodos_fiscales p "
                    "WHERE p.contribuyente_id = t.contribuyente_id)"
                )
            ).scalars().all()
            for contribuyente_id in sin_periodo:
                conexion.execute(
                    text(
                        "INSERT INTO periodos_fiscales (anio_gravable, estado, contribuyente_id) "
                        "VALUES (:anio, 'ABIERTO', :cid)"
                    ),
                    {"anio": anio_por_defecto, "cid": contribuyente_id},
                )

            if tabla == "activos":
                conexion.execute(
                    text(
                        "UPDATE activos a SET periodo_fiscal_id = c.periodo_fiscal_id "
                        "FROM cierres_periodo c WHERE c.activo_inventario_id = a.id"
                    )
                )
            conexion.execute(
                text(
                    f"UPDATE {tabla} t SET periodo_fiscal_id = ("
                    "SELECT p.id FROM periodos_fiscales p "
                    "WHERE p.contribuyente_id = t.contribuyente_id "
                    "ORDER BY p.anio_gravable DESC LIMIT 1) "
                    "WHERE t.periodo_fiscal_id IS NULL"
                )
            )
            conexion.execute(text(f"ALTER TABLE {tabla} ALTER COLUMN periodo_fiscal_id SET NOT NULL"))
            conexion.execute(
                text(
                    f"ALTER TABLE {tabla} ADD CONSTRAINT {tabla}_periodo_fiscal_id_fkey "
                    "FOREIGN KEY (periodo_fiscal_id) REFERENCES periodos_fiscales (id)"
                )
            )
            conexion.execute(
                text(f"CREATE INDEX ix_{tabla}_periodo_fiscal_id ON {tabla} (periodo_fiscal_id)")
            )


def _agregar_columnas_si_faltan(motor, tabla: str, columnas: dict) -> None:
    inspector = inspect(motor)
    if tabla not in inspector.get_table_names():
        return
    existentes = {c["name"] for c in inspector.get_columns(tabla)}
    with motor.begin() as conexion:
        for nombre, tipo in columnas.items():
            if nombre not in existentes:
                conexion.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}"))


def tipos_enum_nativos() -> dict:
    """Los tipos ENUM nativos del esquema, con los valores que debería tener
    cada uno.

    Se lee del metadata y no de una lista escrita a mano: una lista hay que
    acordarse de actualizarla, y el día que alguien agregue un valor a
    cualquier enum del proyecto nadie se va a acordar.
    """
    tipos: dict = {}
    registrar_modelos()
    for tabla in SQLModel.metadata.tables.values():
        for columna in tabla.columns:
            tipo = columna.type
            if isinstance(tipo, EnumSQL) and tipo.native_enum and tipo.name:
                tipos.setdefault(tipo.name, set()).update(tipo.enums)
    return tipos


def _sincronizar_enums(motor) -> None:
    """Agrega a los tipos ENUM de Postgres los valores que les falten.

    Por qué hace falta
    ------------------
    En Postgres, un campo tipado con un Enum de Python se crea como un tipo
    ENUM NATIVO. `create_all` crea ese tipo la primera vez, con los valores
    que existían ese día, y **nunca lo altera**: agregarle un valor al Enum de
    Python no lo agrega al tipo de la base. Guardar el valor nuevo falla con
    `InvalidTextRepresentation`, que le llega al usuario como un 500.

    No se ve en las pruebas porque corren sobre una base que se crea de cero
    en cada corrida, con el tipo ya completo. Solo aparece en una base que
    lleva tiempo viva, que es justo donde duele.

    Esto recorre el metadata y sincroniza TODOS los tipos enum, no solo los
    que cambiaron hoy: así el próximo valor que alguien agregue a cualquier
    enum ya queda cubierto sin que haya que acordarse de escribir su
    migración.
    """
    if motor.dialect.name != "postgresql":
        # En SQLite el enum es un VARCHAR con CHECK: no hay tipo que alterar.
        return

    tipos = tipos_enum_nativos()

    # ALTER TYPE ... ADD VALUE no puede convivir con el uso del valor nuevo en
    # la misma transacción, así que va en autocommit y aparte del create_all.
    with motor.connect() as conexion:
        conexion = conexion.execution_options(isolation_level="AUTOCOMMIT")
        for nombre, valores in tipos.items():
            existentes = {
                fila[0]
                for fila in conexion.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = :tipo"
                    ),
                    {"tipo": nombre},
                )
            }
            if not existentes:
                # El tipo no existe todavía: lo crea `create_all` completo.
                continue
            for valor in sorted(valores - existentes):
                # El valor sale de nuestras propias clases Enum, no de nadie
                # de afuera; se valida igual porque no se puede parametrizar.
                if not valor.replace("_", "").isalnum():
                    raise ValueError(f"Valor de enum no válido: {valor!r}")
                conexion.execute(text(f"ALTER TYPE {nombre} ADD VALUE '{valor}'"))


def crear_tablas() -> None:
    registrar_modelos()
    SQLModel.metadata.create_all(engine)
    _sincronizar_enums(engine)
    _migrar_periodo_en_activos_y_fuentes(engine)
    _agregar_columnas_si_faltan(
        engine,
        "periodos_fiscales",
        {"fecha_vencimiento_manual": "DATE", "fecha_presentacion": "DATE"},
    )
    # Columnas agregadas después de la primera versión. create_all no altera
    # tablas existentes. DEFAULT y NOT NULL para las filas existentes.
    _agregar_columnas_si_faltan(
        engine,
        "hojas_liquidacion",
        {
            "metodo_anticipo": "VARCHAR NOT NULL DEFAULT 'DIRECTO'",
            "reduccion_sancion": "VARCHAR NOT NULL DEFAULT 'NINGUNA'",
            "ingresos_no_constitutivos_capital": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "costos_y_gastos_capital": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "ingresos_no_constitutivos_no_laborales": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "devoluciones_no_laborales": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "costos_y_gastos_no_laborales": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "impuesto_neto_anio_anterior": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "total_pagos_del_anio": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "pagos_en_efectivo": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "patrimonio_liquido_anterior_manual": "NUMERIC(18,2)",
            "impuestos_pagados_en_el_anio": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "justificaciones_patrimoniales": "NUMERIC(18,2) NOT NULL DEFAULT 0",
            "aceptar_renta_comparacion_patrimonial": "BOOLEAN NOT NULL DEFAULT FALSE",
            "cedula_depreciacion": "VARCHAR NOT NULL DEFAULT 'NO_LABORAL'",
        },
    )
    _agregar_columnas_si_faltan(
        engine,
        "deducciones_solicitadas",
        {
            "codigo_plantilla": "VARCHAR",
            # Columna y fila del 210. NULL en las existentes: las imputa el motor.
            "subcedula": "VARCHAR",
            "fila_formulario": "VARCHAR",
        },
    )
    _agregar_columnas_si_faltan(
        engine,
        "registros_exogena",
        {"renglones_son_condicionales": "BOOLEAN NOT NULL DEFAULT FALSE"},
    )
    # Versionado de la exógena por fecha de corte. Los reportes importados
    # antes de esta versión quedan con fecha_corte NULL (no se puede inventar
    # una) y version 1; `obtener_reporte_mas_reciente` los ordena al final
    # justamente por eso.
    _agregar_columnas_si_faltan(
        engine,
        "reportes_exogena",
        {"fecha_corte": "DATE", "version": "INTEGER NOT NULL DEFAULT 1"},
    )
    # El documento solicitado pasó a ser también la cara que ve el cliente:
    # guarda lo que él informó y quién puso el estado.
    _agregar_columnas_si_faltan(
        engine,
        "documentos_solicitados",
        {
            "valor_informado": "NUMERIC(18,2)",
            "respondido_por_contribuyente": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
    )


def obtener_sesion() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
