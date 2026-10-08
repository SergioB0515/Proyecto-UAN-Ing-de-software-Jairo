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


def _crear_periodo(client, token: str, contribuyente_id: int, anio: int = 2025) -> int:
    return client.post(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales",
        json={"anio_gravable": anio},
        headers=_headers(token),
    ).json()["id"]


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
    periodo_id = _crear_periodo(client, token, contribuyente_id)

    client.post(
        f"/contribuyentes/{contribuyente_id}/activos",
        json={
            "descripcion": "Apartamento",
            "tipo": "INMUEBLE",
            "valor": 120000000,
            "periodo_fiscal_id": periodo_id,
        },
        headers=_headers(token),
    )
    client.post(
        f"/contribuyentes/{contribuyente_id}/activos",
        json={
            "periodo_fiscal_id": periodo_id,
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
    assert respuesta.json()["anio_gravable"] == 2025


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

    periodo_id = _crear_periodo(client, token, contribuyente["id"])

    respuesta = client.post(
        f"/contribuyentes/{contribuyente['id']}/activos",
        json={
            "descripcion": "Activo inválido",
            "tipo": "CUENTA",
            "valor": -100,
            "periodo_fiscal_id": periodo_id,
        },
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
    periodo_id = _crear_periodo(client, token, contribuyente_id)

    creada = client.post(
        f"/contribuyentes/{contribuyente_id}/fuentes-ingreso",
        json={
            "periodo_fiscal_id": periodo_id,
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
    assert listado.json()[0]["periodo_fiscal_id"] == periodo_id


def test_agregar_activo_a_contribuyente_inexistente_falla(client):
    token = _crear_contador_y_token(client, "contadorG@example.com")

    respuesta = client.post(
        "/contribuyentes/999999/activos",
        json={"descripcion": "Fantasma", "tipo": "CUENTA", "valor": 1000, "periodo_fiscal_id": 1},
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


# ------------------------------------------------- HU-03: asociación a periodo


def _contribuyente_con_dos_periodos(client, email: str) -> tuple:
    token = _crear_contador_y_token(client, email)
    contribuyente_id = client.post(
        "/contribuyentes",
        json={"nombre": "Dos años", "rut": "9000000000", "tipo_contribuyente": "ASALARIADO"},
        headers=_headers(token),
    ).json()["id"]
    p2024 = _crear_periodo(client, token, contribuyente_id, 2024)
    p2025 = _crear_periodo(client, token, contribuyente_id, 2025)
    return token, contribuyente_id, p2024, p2025


def test_fuente_de_ingreso_sin_periodo_falla(client):
    token = _crear_contador_y_token(client, "hu03-1@example.com")
    contribuyente_id = client.post(
        "/contribuyentes",
        json={"nombre": "Sin periodo", "rut": "9100000000", "tipo_contribuyente": "ASALARIADO"},
        headers=_headers(token),
    ).json()["id"]

    respuesta = client.post(
        f"/contribuyentes/{contribuyente_id}/fuentes-ingreso",
        json={"concepto": "Salario", "valor_anual": 1000},
        headers=_headers(token),
    )
    assert respuesta.status_code == 422


def test_fuentes_y_patrimonio_se_separan_por_periodo(client):
    token, cid, p2024, p2025 = _contribuyente_con_dos_periodos(client, "hu03-2@example.com")
    h = _headers(token)
    for periodo_id, valor in [(p2024, 40000000), (p2025, 50000000)]:
        client.post(
            f"/contribuyentes/{cid}/fuentes-ingreso",
            json={"concepto": "Salario", "valor_anual": valor, "periodo_fiscal_id": periodo_id},
            headers=h,
        )
        client.post(
            f"/contribuyentes/{cid}/activos",
            json={"descripcion": "Cuenta", "tipo": "CUENTA", "valor": valor / 10,
                  "periodo_fiscal_id": periodo_id},
            headers=h,
        )

    fuentes_2024 = client.get(
        f"/contribuyentes/{cid}/fuentes-ingreso?periodo_fiscal_id={p2024}", headers=h
    ).json()
    assert [f["valor_anual"] for f in fuentes_2024] == [40000000]
    assert len(client.get(f"/contribuyentes/{cid}/fuentes-ingreso", headers=h).json()) == 2

    patrimonio_2024 = client.get(
        f"/contribuyentes/{cid}/patrimonio?periodo_fiscal_id={p2024}", headers=h
    ).json()
    assert patrimonio_2024["patrimonio_liquido"] == 4000000
    # Sin periodo explícito: el más reciente.
    assert client.get(f"/contribuyentes/{cid}/patrimonio", headers=h).json()[
        "patrimonio_liquido"
    ] == 5000000

    resumen_2024 = client.get(
        f"/contribuyentes/{cid}/periodos-fiscales/{p2024}/resumen", headers=h
    ).json()
    assert resumen_2024["ingresos"]["total_ingresos"] == 40000000
    assert resumen_2024["patrimonio"]["patrimonio_liquido"] == 4000000


def test_no_se_registra_en_un_periodo_de_otro_contribuyente(client):
    token, cid, p2024, _ = _contribuyente_con_dos_periodos(client, "hu03-3@example.com")
    otro = client.post(
        "/contribuyentes",
        json={"nombre": "Otro", "rut": "9200000000", "tipo_contribuyente": "ASALARIADO"},
        headers=_headers(token),
    ).json()["id"]

    respuesta = client.post(
        f"/contribuyentes/{otro}/activos",
        json={"descripcion": "Cuenta", "tipo": "CUENTA", "valor": 1000, "periodo_fiscal_id": p2024},
        headers=_headers(token),
    )
    assert respuesta.status_code == 404


def test_no_se_registra_en_un_periodo_cerrado(client):
    token, cid, p2024, _ = _contribuyente_con_dos_periodos(client, "hu03-4@example.com")
    client.post(f"/contribuyentes/{cid}/periodos-fiscales/{p2024}/cerrar", headers=_headers(token))

    respuesta = client.post(
        f"/contribuyentes/{cid}/fuentes-ingreso",
        json={"concepto": "Salario", "valor_anual": 1000, "periodo_fiscal_id": p2024},
        headers=_headers(token),
    )
    assert respuesta.status_code == 409


def test_patrimonio_sin_periodos_es_cero(client):
    token = _crear_contador_y_token(client, "hu03-5@example.com")
    cid = client.post(
        "/contribuyentes",
        json={"nombre": "Nuevo", "rut": "9300000000", "tipo_contribuyente": "ASALARIADO"},
        headers=_headers(token),
    ).json()["id"]

    cuerpo = client.get(f"/contribuyentes/{cid}/patrimonio", headers=_headers(token)).json()
    assert cuerpo["patrimonio_liquido"] == 0
    assert cuerpo["periodo_fiscal_id"] is None


def test_obtener_contribuyente_por_id_solo_si_es_propio(client):
    token_a = _crear_contador_y_token(client, "get-1a@example.com")
    token_b = _crear_contador_y_token(client, "get-1b@example.com")
    cid = client.post(
        "/contribuyentes",
        json={"nombre": "Propio", "rut": "9400000000", "tipo_contribuyente": "MIXTO"},
        headers=_headers(token_a),
    ).json()["id"]

    propio = client.get(f"/contribuyentes/{cid}", headers=_headers(token_a))
    ajeno = client.get(f"/contribuyentes/{cid}", headers=_headers(token_b))

    assert propio.status_code == 200
    assert propio.json()["nombre"] == "Propio"
    assert ajeno.status_code == 404
