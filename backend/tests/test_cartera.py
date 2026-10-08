"""Pruebas del panel de cartera (HU-18)."""
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


def _contribuyente(client, h, nombre, anio=2025, importar=False) -> int:
    cid = client.post(
        "/contribuyentes",
        json={"nombre": nombre, "rut": "1000000000", "tipo_contribuyente": "ASALARIADO"},
        headers=h,
    ).json()["id"]
    if anio is None:
        return cid
    pid = client.post(
        f"/contribuyentes/{cid}/periodos-fiscales", json={"anio_gravable": anio}, headers=h
    ).json()["id"]
    if importar:
        with open(RUTA_FIXTURE, "rb") as archivo:
            client.post(
                f"/contribuyentes/{cid}/periodos-fiscales/{pid}/exogena",
                files={"archivo": ("exogena.xlsx", archivo, "application/octet-stream")},
                headers=h,
            )
    return cid


def _registrar_umbral(client, h, valor_uvt=49799):
    client.post(
        "/parametros/umbrales",
        json={
            "anio_gravable": 2025, "valor_uvt": valor_uvt, "tope_ingresos_uvt": 1400,
            "tope_patrimonio_uvt": 4500, "tope_consumo_tc_uvt": 1400,
            "tope_compras_uvt": 1400, "tope_movimiento_uvt": 1400,
        },
        headers=h,
    )


def test_panel_ordena_por_alertas(client):
    h = _headers(_crear_contador_y_token(client, "cartera-1@example.com"))
    _registrar_umbral(client, h)
    _contribuyente(client, h, "Ana sin periodo", anio=None)
    _contribuyente(client, h, "Beto sin exógena")
    con_alertas = _contribuyente(client, h, "Carla con exógena", importar=True)
    # Declara el avalúo y la venta: le quedan menos alertas que a Diego.
    for ruta, datos in [
        ("activos", {"descripcion": "Casa", "tipo": "INMUEBLE", "valor": 120000000, "vinculo_codigo_concepto": "1476"}),
        ("fuentes-ingreso", {"concepto": "Venta", "valor_anual": 50000000, "vinculo_codigo_concepto": "1032"}),
    ]:
        client.post(f"/contribuyentes/{con_alertas}/{ruta}", json=datos, headers=h)
    _contribuyente(client, h, "Diego con exógena", importar=True)

    respuesta = client.get("/cartera", headers=h)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    nombres = [f["nombre"] for f in cuerpo["contribuyentes"]]
    # Más alertas primero; los que no se pueden evaluar al final.
    assert nombres == ["Diego con exógena", "Carla con exógena", "Ana sin periodo", "Beto sin exógena"]
    filas = {f["nombre"]: f for f in cuerpo["contribuyentes"]}
    assert filas["Diego con exógena"]["alertas_no_declarado"] == 5
    assert filas["Carla con exógena"]["alertas_no_declarado"] == 3
    assert filas["Diego con exógena"]["obligado"] is False
    assert filas["Beto sin exógena"]["obligado"] is None
    assert filas["Beto sin exógena"]["avisos"]
    assert filas["Ana sin periodo"]["periodo_fiscal_id"] is None
    assert cuerpo["total_contribuyentes"] == 4
    assert cuerpo["total_alertas"] == 8


def test_panel_ordena_por_nombre(client):
    h = _headers(_crear_contador_y_token(client, "cartera-2@example.com"))
    _contribuyente(client, h, "zeta", importar=True)
    _contribuyente(client, h, "Alfa")

    cuerpo = client.get("/cartera?orden=nombre", headers=h).json()

    assert [f["nombre"] for f in cuerpo["contribuyentes"]] == ["Alfa", "zeta"]


def test_panel_cuenta_obligados(client):
    h = _headers(_crear_contador_y_token(client, "cartera-3@example.com"))
    # Umbral bajísimo a propósito para forzar "obligado".
    _registrar_umbral(client, h, valor_uvt=1)
    _contribuyente(client, h, "Obligado", importar=True)

    cuerpo = client.get("/cartera?anio_gravable=2025", headers=h).json()

    assert cuerpo["anio_gravable"] == 2025
    assert cuerpo["total_obligados"] == 1
    assert cuerpo["contribuyentes"][0]["obligado"] is True


def test_panel_con_anio_sin_periodo(client):
    h = _headers(_crear_contador_y_token(client, "cartera-4@example.com"))
    _contribuyente(client, h, "Solo 2025")

    fila = client.get("/cartera?anio_gravable=2024", headers=h).json()["contribuyentes"][0]

    assert fila["periodo_fiscal_id"] is None
    assert "2024" in fila["avisos"][0]


def test_panel_solo_muestra_contribuyentes_propios(client):
    h_a = _headers(_crear_contador_y_token(client, "cartera-5a@example.com"))
    h_b = _headers(_crear_contador_y_token(client, "cartera-5b@example.com"))
    _contribuyente(client, h_a, "De A", importar=True)

    cuerpo = client.get("/cartera", headers=h_b).json()

    assert cuerpo["contribuyentes"] == []
    assert cuerpo["total_alertas"] == 0


def test_panel_sin_token_falla(client):
    assert client.get("/cartera").status_code == 401
