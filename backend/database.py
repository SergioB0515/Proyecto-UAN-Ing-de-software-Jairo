"""Engine de SQLModel sobre PostgreSQL. Ver documentacion/04-arquitectura.md."""
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from core.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)


def crear_tablas() -> None:
    """Crea las tablas que todavía no existan. Se llama al arrancar la
    aplicación (ver main.py). Sin Alembic en este incremento: un cambio de
    esquema exige recrear la base de datos, igual que en el otro proyecto
    del curso."""
    # Importa los modelos aquí (no arriba del todo) para que SQLModel los
    # conozca antes de crear las tablas, sin crear un import circular con
    # los módulos que a su vez importan `database`.
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
    from modulos.parametros.modelos import UmbralDeclaracion  # noqa: F401

    SQLModel.metadata.create_all(engine)


def obtener_sesion() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    with Session(engine) as session:
        yield session
