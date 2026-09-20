"""Pruebas del módulo de exógena.

Las de `parsear_archivo_exogena` no necesitan base de datos — son sobre una
función pura. Las de importación sí, porque pasan por el endpoint real.
"""
import io
from pathlib import Path

import openpyxl
import pytest

from core.excepciones import ArchivoExogenaInvalidoError
from modulos.exogena.servicios import parsear_archivo_exogena

RUTA_FIXTURE = Path(__file__).parent / "fixtures" / "reporte_exogena_ejemplo.xlsx"


def _leer_fixture() -> bytes:
    return RUTA_FIXTURE.read_bytes()


def _buscar_registro(resultado, contiene: str):
    """Ayuda para los tests: el primer registro cuyo detalle contiene el
    texto dado."""
    return next(r for r in resultado.registros if contiene in r.detalle)


# ---------------------------------------------------- parsear_archivo_exogena


def test_parsear_detecta_al_consultante():
    resultado = parsear_archivo_exogena(_leer_fixture())
    assert resultado.consultante.identificacion == "1000000000"
    assert resultado.consultante.nombre == "CONTRIBUYENTE EJEMPLO"


def test_parsear_separa_topes_de_registros():
    resultado = parsear_archivo_exogena(_leer_fixture())
    # El fixture tiene 5 topes y 10 registros de detalle — ver
    # tests/fixtures/reporte_exogena_ejemplo.xlsx.
    assert len(resultado.topes) == 5
    assert len(resultado.registros) == 10
    assert len(resultado.errores) == 0


def test_parsear_topes_tienen_las_cinco_categorias():
    resultado = parsear_archivo_exogena(_leer_fixture())
    etiquetas = " ".join(t.etiqueta for t in resultado.topes).lower()
    for palabra in ["ingreso", "patrimonio", "consumo", "movimiento", "compra"]:
        assert palabra in etiquetas


def test_parsear_extrae_codigo_de_concepto_cuando_esta_presente():
    resultado = parsear_archivo_exogena(_leer_fixture())
    avaluo = _buscar_registro(resultado, "avalúo catastral")
    assert avaluo.concepto_code == "1476"


def test_parsear_deja_concepto_en_none_cuando_no_esta_presente():
    resultado = parsear_archivo_exogena(_leer_fixture())
    movimientos = _buscar_registro(resultado, "movimientos en cuentas")
    assert movimientos.concepto_code is None


def test_parsear_extrae_renglones_sugeridos():
    resultado = parsear_archivo_exogena(_leer_fixture())
    venta = _buscar_registro(resultado, "Ingreso por venta")
    assert venta.renglones_sugeridos is not None
    assert "R112" in venta.renglones_sugeridos


def test_parsear_marca_fila_autoreportada():
    resultado = parsear_archivo_exogena(_leer_fixture())
    saldo_a_favor = _buscar_registro(resultado, "Total saldo a favor")
    assert saldo_a_favor.es_auto_reportado is True
    assert saldo_a_favor.es_dian is False


def test_parsear_marca_fila_de_la_dian():
    resultado = parsear_archivo_exogena(_leer_fixture())
    facturacion = _buscar_registro(resultado, "facturas tras ajustes")
    assert facturacion.es_dian is True
    assert facturacion.es_auto_reportado is False


def test_parsear_fila_de_tercero_genuino_no_esta_marcada():
    resultado = parsear_archivo_exogena(_leer_fixture())
    avaluo = _buscar_registro(resultado, "avalúo catastral")
    assert avaluo.es_auto_reportado is False
    assert avaluo.es_dian is False


def test_parsear_archivo_sin_formato_dian_lanza_error():
    # Un .xlsx válido, pero que no es un archivo de la DIAN — no tiene la
    # fila de encabezados "NIT" / "Nombre...".
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja["A1"] = "Esto no es un archivo de la DIAN"
    buffer = io.BytesIO()
    libro.save(buffer)

    with pytest.raises(ArchivoExogenaInvalidoError):
        parsear_archivo_exogena(buffer.getvalue())


# --------------------------------------------------------- importar_reporte_exogena
# (vía el endpoint — necesitan contador, contribuyente y periodo fiscal)


def _crear_contador_y_token(client, email: str) -> str:
    client.post(
        "/contadores/registro",
        json={"nombre": "Contador de prueba", "email": email, "contrasena": "claveDePrueba1"},
    )
    login = client.post(
        "/contadores/login", data={"username": email, "password": "claveDePrueba1"}
    )
    return login.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _crear_contribuyente_con_periodo(client, token: str) -> tuple:
    contribuyente = client.post(
        "/contribuyentes",
        json={
            "nombre": "Contribuyente Ejemplo",
            "rut": "1000000000",
            "tipo_contribuyente": "INDEPENDIENTE",
        },
        headers=_headers(token),
    ).json()
    periodo = client.post(
        f"/contribuyentes/{contribuyente['id']}/periodos-fiscales",
        json={"anio_gravable": 2025},
        headers=_headers(token),
    ).json()
    return contribuyente["id"], periodo["id"]


def _subir_fixture(client, token, contribuyente_id, periodo_fiscal_id):
    with open(RUTA_FIXTURE, "rb") as archivo:
        return client.post(
            f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_fiscal_id}/exogena",
            files={
                "archivo": (
                    "reporte_exogena_ejemplo.xlsx",
                    archivo,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            headers=_headers(token),
        )


def test_importar_exogena_crea_el_reporte(client):
    token = _crear_contador_y_token(client, "exogena-a@example.com")
    contribuyente_id, periodo_id = _crear_contribuyente_con_periodo(client, token)

    respuesta = _subir_fixture(client, token, contribuyente_id, periodo_id)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre_archivo_original"] == "reporte_exogena_ejemplo.xlsx"
    assert cuerpo["contribuyente_id"] == contribuyente_id
    assert cuerpo["periodo_fiscal_id"] == periodo_id


def test_importar_exogena_persiste_los_registros(client):
    token = _crear_contador_y_token(client, "exogena-b@example.com")
    contribuyente_id, periodo_id = _crear_contribuyente_con_periodo(client, token)
    reporte = _subir_fixture(client, token, contribuyente_id, periodo_id).json()

    registros = client.get(
        f"/contribuyentes/{contribuyente_id}/reportes-exogena/{reporte['id']}/registros",
        headers=_headers(token),
    )

    assert registros.status_code == 200
    assert len(registros.json()) == 10


def test_listar_registros_filtra_por_concepto(client):
    token = _crear_contador_y_token(client, "exogena-c@example.com")
    contribuyente_id, periodo_id = _crear_contribuyente_con_periodo(client, token)
    reporte = _subir_fixture(client, token, contribuyente_id, periodo_id).json()

    registros = client.get(
        f"/contribuyentes/{contribuyente_id}/reportes-exogena/{reporte['id']}/registros"
        "?concepto_code=1476",
        headers=_headers(token),
    )

    assert registros.status_code == 200
    assert len(registros.json()) == 1
    assert "avalúo catastral" in registros.json()[0]["detalle"]


def test_importar_exogena_a_contribuyente_ajeno_falla(client):
    token_a = _crear_contador_y_token(client, "exogena-d1@example.com")
    token_b = _crear_contador_y_token(client, "exogena-d2@example.com")
    contribuyente_id, periodo_id = _crear_contribuyente_con_periodo(client, token_a)

    respuesta = _subir_fixture(client, token_b, contribuyente_id, periodo_id)

    assert respuesta.status_code == 404


def test_importar_exogena_con_periodo_fiscal_inexistente_falla(client):
    token = _crear_contador_y_token(client, "exogena-e@example.com")
    contribuyente_id, _ = _crear_contribuyente_con_periodo(client, token)

    respuesta = _subir_fixture(client, token, contribuyente_id, 999999)

    assert respuesta.status_code == 404


def test_importar_archivo_sin_formato_dian_devuelve_422(client):
    token = _crear_contador_y_token(client, "exogena-f@example.com")
    contribuyente_id, periodo_id = _crear_contribuyente_con_periodo(client, token)

    libro = openpyxl.Workbook()
    libro.active["A1"] = "no es un archivo de la DIAN"
    buffer = io.BytesIO()
    libro.save(buffer)
    buffer.seek(0)

    respuesta = client.post(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/exogena",
        files={"archivo": ("otro.xlsx", buffer, "application/octet-stream")},
        headers=_headers(token),
    )

    assert respuesta.status_code == 422
