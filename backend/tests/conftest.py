import os
import shutil
import tempfile

os.environ.setdefault("JWT_SECRET_KEY", "clave-de-pruebas-no-usar-en-produccion")
ALMACEN_PRUEBAS = tempfile.mkdtemp(prefix="almacen_pruebas_")
os.environ["ALMACEN_ADJUNTOS"] = ALMACEN_PRUEBAS

if "TEST_DATABASE_URL" not in os.environ:
    from dotenv import load_dotenv

    load_dotenv()
    url_desarrollo = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/renta_db"
    )
    os.environ["TEST_DATABASE_URL"] = url_desarrollo.rsplit("/", 1)[0] + "/renta_test_db"

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from core.config import DATABASE_URL
from database import obtener_sesion, registrar_modelos
from main import app

registrar_modelos()

_engine_pruebas = create_engine(DATABASE_URL)


@pytest.fixture(scope="session", autouse=True)
def _preparar_esquema():
    SQLModel.metadata.create_all(_engine_pruebas)
    yield
    SQLModel.metadata.drop_all(_engine_pruebas)
    shutil.rmtree(ALMACEN_PRUEBAS, ignore_errors=True)


@pytest.fixture()
def session():
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
    def _sesion_de_prueba():
        yield session

    app.dependency_overrides[obtener_sesion] = _sesion_de_prueba
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()
