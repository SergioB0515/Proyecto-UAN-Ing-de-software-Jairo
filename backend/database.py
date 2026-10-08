"""Engine de SQLModel sobre PostgreSQL. Ver documentacion/04-arquitectura.md."""
from typing import Iterator

from datetime import date

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from core.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)


def registrar_modelos() -> None:
    """Importa todos los modelos con tabla para que SQLModel.metadata los
    conozca. Se importan aquí (no arriba del todo) para no crear un import
    circular con los módulos que a su vez importan `database`. Lo usan
    crear_tablas y tests/conftest.py — un modelo nuevo se agrega solo aquí."""
    from modulos.auditoria.modelos import EventoAuditoria, IntentoAcceso  # noqa: F401
    from modulos.contadores.modelos import Contador  # noqa: F401
    from modulos.contribuyentes.modelos import (  # noqa: F401
        Activo,
        Contribuyente,
        FuenteIngreso,
        PeriodoFiscal,
    )
    from modulos.exogena.modelos import (  # noqa: F401
        ConceptoDian,
        RegistroExogena,
        ReporteExogena,
        TopeExogena,
    )
    from modulos.inventario.modelos import Categoria, Producto  # noqa: F401
    from modulos.movimientos.modelos import (  # noqa: F401
        DocumentoSoporte,
        Movimiento,
        Proveedor,
    )
    from modulos.parametros.modelos import UmbralDeclaracion  # noqa: F401
    from modulos.reportes.modelos import CierrePeriodo  # noqa: F401


def _migrar_periodo_en_activos_y_fuentes(motor) -> None:
    """Migración puntual (HU-03): `activos` y `fuentes_ingreso` pasaron a
    tener `periodo_fiscal_id`. Si la base es anterior a ese cambio:

    1. Agrega la columna.
    2. Asigna el Activo INVENTARIO de cada cierre a su periodo, y el resto
       de filas al periodo más reciente de su contribuyente; si el contribuyente no tiene periodos, le crea uno
       ABIERTO para el año anterior al actual (el que normalmente se
       declara).
    3. Deja la columna como NOT NULL con su llave foránea.

    Es idempotente: si la columna ya existe no hace nada. Se mantiene aquí
    en vez de introducir Alembic para un solo cambio de esquema."""
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
                # El inventario que creó un cierre va al periodo de ese cierre.
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


def crear_tablas() -> None:
    """Crea las tablas que todavía no existan y aplica las migraciones
    puntuales pendientes. Se llama al arrancar la aplicación (ver main.py).
    Sin Alembic: `create_all` crea tablas nuevas pero no agrega columnas a
    tablas que ya existen — por eso los cambios a tablas existentes van en
    funciones `_migrar_*` idempotentes como la de abajo."""
    registrar_modelos()
    SQLModel.metadata.create_all(engine)
    _migrar_periodo_en_activos_y_fuentes(engine)


def obtener_sesion() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    with Session(engine) as session:
        yield session
