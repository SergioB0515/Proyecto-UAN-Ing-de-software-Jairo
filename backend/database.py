"""Engine de SQLModel sobre PostgreSQL. Ver documentacion/04-arquitectura.md."""
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from core.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)


def registrar_modelos() -> None:
    """Importa todos los modelos con tabla para que SQLModel.metadata los
    conozca. Se importan aquí (no arriba del todo) para no crear un import
    circular con los módulos que a su vez importan `database`. Lo usan
    crear_tablas y tests/conftest.py — un modelo nuevo se agrega solo aquí."""
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


def crear_tablas() -> None:
    """Crea las tablas que todavía no existan. Se llama al arrancar la
    aplicación (ver main.py). Sin Alembic: `create_all` crea tablas nuevas
    pero no agrega columnas a tablas que ya existen — un cambio en una
    tabla existente exige recrear la base de datos."""
    registrar_modelos()
    SQLModel.metadata.create_all(engine)


def obtener_sesion() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    with Session(engine) as session:
        yield session
