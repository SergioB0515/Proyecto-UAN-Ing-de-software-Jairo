"""Pruebas del módulo de parámetros: CRUD de umbrales (ya implementado) y
verificación de obligación de declarar (el objetivo a cumplir)."""
from pathlib import Path

RUTA_FIXTURE = Path(__file__).parent / "fixtures" / "reporte_exogena_ejemplo.xlsx"


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


def _crear_contribuyente_con_periodo(client, token: str, anio_gravable: int = 2025) -> tuple:
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
        json={"anio_gravable": anio_gravable},
        headers=_headers(token),
    ).json()
    return contribuyente["id"], periodo["id"]


def _importar_fixture(client, token, contribuyente_id, periodo_id):
    with open(RUTA_FIXTURE, "rb") as archivo:
        client.post(
            f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/exogena",
            files={
                "archivo": (
                    "reporte_exogena_ejemplo.xlsx",
                    archivo,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            headers=_headers(token),
        )


# ------------------------------------------------------------------- Umbrales
# (ya implementado — estas deberían pasar sin que toques nada)


def test_registrar_y_listar_umbral(client):
    token = _crear_contador_y_token(client, "parametros-a@example.com")

    creado = client.post(
        "/parametros/umbrales",
        json={
            "anio_gravable": 2025,
            "valor_uvt": 49799,
            "tope_ingresos_uvt": 1400,
            "tope_patrimonio_uvt": 4500,
            "tope_consumo_tc_uvt": 1400,
            "tope_compras_uvt": 1400,
            "tope_movimiento_uvt": 1400,
        },
        headers=_headers(token),
    )
    assert creado.status_code == 201

    listado = client.get("/parametros/umbrales", headers=_headers(token))
    anios = [u["anio_gravable"] for u in listado.json()]
    assert 2025 in anios


# ------------------------------------------------------- Obligación de declarar
# (el objetivo a cumplir)


def test_verificar_obligacion_no_obligado_con_umbrales_reales(client):
    token = _crear_contador_y_token(client, "parametros-b@example.com")
    contribuyente_id, periodo_id = _crear_contribuyente_con_periodo(client, token, 2025)
    _importar_fixture(client, token, contribuyente_id, periodo_id)

    client.post(
        "/parametros/umbrales",
        json={
            "anio_gravable": 2025,
            "valor_uvt": 49799,
            "tope_ingresos_uvt": 1400,
            "tope_patrimonio_uvt": 4500,
            "tope_consumo_tc_uvt": 1400,
            "tope_compras_uvt": 1400,
            "tope_movimiento_uvt": 1400,
        },
        headers=_headers(token),
    )

    respuesta = client.get(
        f"/parametros/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/obligacion",
        headers=_headers(token),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    # Con los topes de umbral reales de 2025, ninguno de los valores del
    # fixture los supera — contribuyente ficticio, valores deliberadamente
    # por debajo.
    assert cuerpo["obligado"] is False
    assert len(cuerpo["criterios"]) == 5
    criterios = {c["criterio"]: c for c in cuerpo["criterios"]}
    assert "Ingresos" in criterios
    assert "Patrimonio" in criterios
    assert criterios["Ingresos"]["valor_reportado"] == 50000000


def test_verificar_obligacion_obligado_con_umbrales_bajos(client):
    token = _crear_contador_y_token(client, "parametros-c@example.com")
    contribuyente_id, periodo_id = _crear_contribuyente_con_periodo(client, token, 2026)
    _importar_fixture(client, token, contribuyente_id, periodo_id)

    # Umbrales deliberadamente bajos para forzar el caso "sí obligado" y
    # probar la lógica de comparación, no un caso real de la DIAN.
    client.post(
        "/parametros/umbrales",
        json={
            "anio_gravable": 2026,
            "valor_uvt": 1,
            "tope_ingresos_uvt": 1000,
            "tope_patrimonio_uvt": 1000,
            "tope_consumo_tc_uvt": 1000,
            "tope_compras_uvt": 1000,
            "tope_movimiento_uvt": 1000,
        },
        headers=_headers(token),
    )

    respuesta = client.get(
        f"/parametros/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/obligacion",
        headers=_headers(token),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["obligado"] is True
    assert any(c["supera_umbral"] for c in cuerpo["criterios"])


def test_verificar_obligacion_sin_exogena_importada_falla(client):
    token = _crear_contador_y_token(client, "parametros-d@example.com")
    contribuyente_id, periodo_id = _crear_contribuyente_con_periodo(client, token, 2025)
    # Nota: no se importa exógena para este periodo.

    respuesta = client.get(
        f"/parametros/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/obligacion",
        headers=_headers(token),
    )

    assert respuesta.status_code == 404


def test_verificar_obligacion_sin_umbral_configurado_falla(client):
    token = _crear_contador_y_token(client, "parametros-e@example.com")
    # Año 2099 a propósito — casi seguro nadie configuró un umbral para ese año.
    contribuyente_id, periodo_id = _crear_contribuyente_con_periodo(client, token, 2099)
    _importar_fixture(client, token, contribuyente_id, periodo_id)

    respuesta = client.get(
        f"/parametros/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/obligacion",
        headers=_headers(token),
    )

    assert respuesta.status_code == 409
