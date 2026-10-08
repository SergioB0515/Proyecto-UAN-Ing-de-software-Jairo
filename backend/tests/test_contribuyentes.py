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


def test_crear_y_listar_contribuyente(client):
    token = _crear_contador_y_token(client, "contadorA@example.com")

    creado = client.post(
        "/contribuyentes",
        json={
            "nombre": "Contribuyente Ejemplo",
            "rut": "1000000000",
            "tipo_contribuyente": "INDEPENDIENTE",
            "regimen_tributario": "Ordinario",
        },
        headers=_headers(token),
    )
    assert creado.status_code == 201
    assert creado.json()["nombre"] == "Contribuyente Ejemplo"

    listado = client.get("/contribuyentes", headers=_headers(token))
    assert listado.status_code == 200
    assert len(listado.json()) == 1


def test_crear_contribuyente_sin_token_falla(client):
    respuesta = client.post(
        "/contribuyentes",
        json={
            "nombre": "Sin sesión",
            "rut": "9999999999",
            "tipo_contribuyente": "ASALARIADO",
        },
    )
    assert respuesta.status_code == 401


def test_un_contador_no_ve_contribuyentes_de_otro(client):
    token_a = _crear_contador_y_token(client, "contadorB1@example.com")
    token_b = _crear_contador_y_token(client, "contadorB2@example.com")

    client.post(
        "/contribuyentes",
        json={
            "nombre": "Cliente de A",
            "rut": "2000000000",
            "tipo_contribuyente": "ASALARIADO",
        },
        headers=_headers(token_a),
    )

    listado_de_b = client.get("/contribuyentes", headers=_headers(token_b))
    assert listado_de_b.status_code == 200
    assert listado_de_b.json() == []


def test_un_contador_no_puede_ver_el_patrimonio_de_otro(client):
    token_a = _crear_contador_y_token(client, "contadorD1@example.com")
    token_b = _crear_contador_y_token(client, "contadorD2@example.com")

    contribuyente = client.post(
        "/contribuyentes",
        json={
            "nombre": "Cliente privado",
            "rut": "4000000000",
            "tipo_contribuyente": "ASALARIADO",
        },
        headers=_headers(token_a),
    ).json()

    respuesta = client.get(
        f"/contribuyentes/{contribuyente['id']}/patrimonio", headers=_headers(token_b)
    )
    assert respuesta.status_code == 404


def test_patrimonio_liquido_suma_los_activos(client):
    token = _crear_contador_y_token(client, "contadorC@example.com")

    contribuyente = client.post(
        "/contribuyentes",
        json={
            "nombre": "Contribuyente Patrimonio",
            "rut": "3000000000",
            "tipo_contribuyente": "MIXTO",
        },
        headers=_headers(token),
    ).json()
    contribuyente_id = contribuyente["id"]

    client.post(
        f"/contribuyentes/{contribuyente_id}/activos",
        json={"descripcion": "Apartamento", "tipo": "INMUEBLE", "valor": 120000000},
        headers=_headers(token),
    )
    client.post(
        f"/contribuyentes/{contribuyente_id}/activos",
        json={
            "descripcion": "Cuenta de ahorros",
            "tipo": "CUENTA",
            "valor": 3000000,
            "vinculo_palabra_clave": "movimientos en cuentas",
        },
        headers=_headers(token),
    )

    respuesta = client.get(
        f"/contribuyentes/{contribuyente_id}/patrimonio", headers=_headers(token)
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["patrimonio_liquido"] == 123000000


def test_activo_con_valor_negativo_falla(client):
    token = _crear_contador_y_token(client, "contadorE@example.com")
    contribuyente = client.post(
        "/contribuyentes",
        json={
            "nombre": "Contribuyente E",
            "rut": "5000000000",
            "tipo_contribuyente": "ASALARIADO",
        },
        headers=_headers(token),
    ).json()

    respuesta = client.post(
        f"/contribuyentes/{contribuyente['id']}/activos",
        json={"descripcion": "Activo inválido", "tipo": "CUENTA", "valor": -100},
        headers=_headers(token),
    )
    assert respuesta.status_code == 422


def test_agregar_y_listar_fuente_de_ingreso(client):
    token = _crear_contador_y_token(client, "contadorF@example.com")
    contribuyente = client.post(
        "/contribuyentes",
        json={
            "nombre": "Contribuyente F",
            "rut": "6000000000",
            "tipo_contribuyente": "INDEPENDIENTE",
        },
        headers=_headers(token),
    ).json()
    contribuyente_id = contribuyente["id"]

    creada = client.post(
        f"/contribuyentes/{contribuyente_id}/fuentes-ingreso",
        json={
            "concepto": "Venta apartamento (notaría)",
            "valor_anual": 50000000,
            "retencion_fuente": 900000,
            "vinculo_codigo_concepto": "1032",
        },
        headers=_headers(token),
    )
    assert creada.status_code == 201

    listado = client.get(
        f"/contribuyentes/{contribuyente_id}/fuentes-ingreso", headers=_headers(token)
    )
    assert listado.status_code == 200
    assert len(listado.json()) == 1
    assert listado.json()[0]["vinculo_codigo_concepto"] == "1032"


def test_agregar_activo_a_contribuyente_inexistente_falla(client):
    token = _crear_contador_y_token(client, "contadorG@example.com")

    respuesta = client.post(
        "/contribuyentes/999999/activos",
        json={"descripcion": "Fantasma", "tipo": "CUENTA", "valor": 1000},
        headers=_headers(token),
    )
    assert respuesta.status_code == 404


def test_periodo_fiscal_duplicado_falla(client):
    token = _crear_contador_y_token(client, "contadorH@example.com")
    contribuyente = client.post(
        "/contribuyentes",
        json={"nombre": "Contribuyente H", "rut": "8000000000", "tipo_contribuyente": "ASALARIADO"},
        headers=_headers(token),
    ).json()
    url = f"/contribuyentes/{contribuyente['id']}/periodos-fiscales"

    primero = client.post(url, json={"anio_gravable": 2025}, headers=_headers(token))
    segundo = client.post(url, json={"anio_gravable": 2025}, headers=_headers(token))

    assert primero.status_code == 201
    assert segundo.status_code == 409


def test_periodo_fiscal_siempre_nace_abierto(client):
    token = _crear_contador_y_token(client, "contadorI@example.com")
    contribuyente = client.post(
        "/contribuyentes",
        json={"nombre": "Contribuyente I", "rut": "8100000000", "tipo_contribuyente": "ASALARIADO"},
        headers=_headers(token),
    ).json()

    periodo = client.post(
        f"/contribuyentes/{contribuyente['id']}/periodos-fiscales",
        json={"anio_gravable": 2025, "estado": "CERRADO"},
        headers=_headers(token),
    )

    assert periodo.status_code == 201
    assert periodo.json()["estado"] == "ABIERTO"
