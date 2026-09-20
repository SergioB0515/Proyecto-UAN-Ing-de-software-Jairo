"""Fixtures compartidas. Las pruebas corren contra una base de datos
PostgreSQL real (no mocks) — cada test corre dentro de una transacción que
se revierte al terminar, así que no necesitas limpiar datos entre pruebas
ni las pruebas se afectan entre sí.

Antes de correr `pytest`, la base de datos de TEST_DATABASE_URL debe
existir (ver backend/README.md).
"""
import os

# Las variables de entorno se fijan ANTES de importar nada de la app, para
# que core.config no falle por falta de JWT_SECRET_KEY y para apuntar a la
# base de datos de pruebas en vez de la de desarrollo.
os.environ.setdefault("JWT_SECRET_KEY", "clave-de-pruebas-no-usar-en-produccion")

# Si no se definió TEST_DATABASE_URL explícitamente, se deriva de DATABASE_URL
# (la de tu .env) reemplazando el nombre de la base por el de pruebas — así
# se respeta tu contraseña real en vez de asumir una fija que probablemente
# no sea la tuya.
if "TEST_DATABASE_URL" not in os.environ:
    from dotenv import load_dotenv

    load_dotenv()
    url_desarrollo = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/renta_db"
    )
    os.environ["TEST_DATABASE_URL"] = url_desarrollo.rsplit("/", 1)[0] + "/renta_test_db"

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from core.config import DATABASE_URL  # noqa: E402
from database import obtener_sesion  # noqa: E402
from main import app  # noqa: E402

# Importar los modelos para que SQLModel.metadata los conozca al crear el
# esquema de pruebas.
from modulos.contadores.modelos import Contador  # noqa: E402,F401
from modulos.contribuyentes.modelos import (  # noqa: E402,F401
    Activo,
    Contribuyente,
    FuenteIngreso,
    PeriodoFiscal,
)
from modulos.exogena.modelos import (  # noqa: E402,F401
    ConceptoDian,
    RegistroExogena,
    ReporteExogena,
    TopeExogena,
)
from modulos.parametros.modelos import UmbralDeclaracion  # noqa: E402,F401

_engine_pruebas = create_engine(DATABASE_URL)


@pytest.fixture(scope="session", autouse=True)
def _preparar_esquema():
    SQLModel.metadata.create_all(_engine_pruebas)
    yield
    SQLModel.metadata.drop_all(_engine_pruebas)


@pytest.fixture()
def session():
    """Una sesión dentro de una transacción que siempre se revierte."""
    conexion = _engine_pruebas.connect()
    transaccion = conexion.begin()
    sesion = Session(bind=conexion)
    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()


@pytest.fixture()
def client(session):
    """Cliente de pruebas de FastAPI, con la sesión de la base de datos
    sustituida por la de la transacción de este test."""

    def _sesion_de_prueba():
        yield session

    app.dependency_overrides[obtener_sesion] = _sesion_de_prueba
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()
