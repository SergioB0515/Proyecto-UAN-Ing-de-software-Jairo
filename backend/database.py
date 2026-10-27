from typing import Iterator

from datetime import date

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from core.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)


def registrar_modelos() -> None:
    from modulos.adjuntos.modelos import Adjunto
    from modulos.auditoria.modelos import EventoAuditoria, IntentoAcceso
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
    from modulos.movimientos.modelos import (
        DocumentoSoporte,
        Movimiento,
        Proveedor,
    )
    from modulos.parametros.modelos import PlazoDeclaracion, UmbralDeclaracion
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


def crear_tablas() -> None:
    registrar_modelos()
    SQLModel.metadata.create_all(engine)
    _migrar_periodo_en_activos_y_fuentes(engine)
    _agregar_columnas_si_faltan(
        engine,
        "periodos_fiscales",
        {"fecha_vencimiento_manual": "DATE", "fecha_presentacion": "DATE"},
    )


def obtener_sesion() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
