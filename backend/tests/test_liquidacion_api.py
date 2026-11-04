"""Pruebas de la API de liquidación.

Cubren lo que el motor no puede cubrir solo: que la hoja persista, que la
clasificación por cédula se respete, que un ingreso sin clasificar se excluya
del cálculo en vez de colarse con una cédula adivinada, y que un contador no
alcance los datos de otro.
"""

from decimal import Decimal as D


def _token(client, email: str) -> dict:
    client.post(
        "/contadores/registro",
        json={"nombre": "Contador", "email": email, "contrasena": "claveDePrueba1"},
    )
    login = client.post(
        "/contadores/login", data={"username": email, "password": "claveDePrueba1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _contribuyente(client, h, anio=2025):
    cid = client.post(
        "/contribuyentes",
        json={"nombre": "Contribuyente", "rut": "1000000012", "tipo_contribuyente": "ASALARIADO"},
        headers=h,
    ).json()["id"]
    pid = client.post(
        f"/contribuyentes/{cid}/periodos-fiscales", json={"anio_gravable": anio}, headers=h
    ).json()["id"]
    return cid, pid


def _base(cid, pid):
    return f"/liquidacion/contribuyentes/{cid}/periodos-fiscales/{pid}"


def _fuente(client, h, cid, pid, concepto, valor, retencion=0):
    return client.post(
        f"/contribuyentes/{cid}/fuentes-ingreso",
        json={
            "concepto": concepto,
            "valor_anual": valor,
            "retencion_fuente": retencion,
            "periodo_fiscal_id": pid,
        },
        headers=h,
    ).json()["id"]


def _valor(liq, codigo):
    return D(next(r["valor"] for r in liq["renglones"] if r["codigo"] == codigo))


# ---------------------------------------------------------------------------
# Hoja de liquidación
# ---------------------------------------------------------------------------


def test_la_hoja_se_crea_vacia_la_primera_vez_que_se_consulta(client):
    h = _token(client, "liq-1@example.com")
    cid, pid = _contribuyente(client, h)

    respuesta = client.get(f"{_base(cid, pid)}/hoja", headers=h)

    assert respuesta.status_code == 200
    hoja = respuesta.json()
    assert hoja["periodo_fiscal_id"] == pid
    assert D(hoja["deudas"]) == D("0")
    assert hoja["numero_dependientes"] == 0
    assert hoja["anios_declarando"] == 3


def test_la_hoja_se_actualiza_parcialmente_y_conserva_lo_demas(client):
    h = _token(client, "liq-2@example.com")
    cid, pid = _contribuyente(client, h)
    client.patch(
        f"{_base(cid, pid)}/hoja",
        json={"numero_dependientes": 2, "deudas": "50000000"},
        headers=h,
    )

    hoja = client.patch(
        f"{_base(cid, pid)}/hoja", json={"numero_dependientes": 3}, headers=h
    ).json()

    assert hoja["numero_dependientes"] == 3
    assert D(hoja["deudas"]) == D("50000000")  # no se borró al no enviarla


def test_la_hoja_rechaza_valores_negativos(client):
    h = _token(client, "liq-3@example.com")
    cid, pid = _contribuyente(client, h)
    respuesta = client.patch(
        f"{_base(cid, pid)}/hoja", json={"deudas": "-1"}, headers=h
    )
    assert respuesta.status_code == 422


# ---------------------------------------------------------------------------
# Deducciones solicitadas
# ---------------------------------------------------------------------------


def test_las_deducciones_se_crean_listan_y_eliminan(client):
    h = _token(client, "liq-4@example.com")
    cid, pid = _contribuyente(client, h)
    creada = client.post(
        f"{_base(cid, pid)}/deducciones",
        json={
            "nombre": "Intereses de vivienda",
            "valor": "12000000",
            "sujeto_a_limite_general": True,
            "fuente_legal": "Art. 119 ET",
        },
        headers=h,
    )
    assert creada.status_code == 201

    listado = client.get(f"{_base(cid, pid)}/deducciones", headers=h).json()
    assert [d["nombre"] for d in listado] == ["Intereses de vivienda"]

    borrado = client.delete(
        f"{_base(cid, pid)}/deducciones/{creada.json()['id']}", headers=h
    )
    assert borrado.status_code == 204
    assert client.get(f"{_base(cid, pid)}/deducciones", headers=h).json() == []


def test_no_se_puede_borrar_una_deduccion_de_otro_periodo(client):
    h = _token(client, "liq-5@example.com")
    cid, pid = _contribuyente(client, h, anio=2025)
    otro_pid = client.post(
        f"/contribuyentes/{cid}/periodos-fiscales", json={"anio_gravable": 2024}, headers=h
    ).json()["id"]
    did = client.post(
        f"{_base(cid, pid)}/deducciones", json={"nombre": "X", "valor": "1000"}, headers=h
    ).json()["id"]

    respuesta = client.delete(f"{_base(cid, otro_pid)}/deducciones/{did}", headers=h)

    assert respuesta.status_code == 404


# ---------------------------------------------------------------------------
# Clasificación por cédula
# ---------------------------------------------------------------------------


def test_los_ingresos_traen_una_cedula_sugerida_y_marcada_como_tal(client):
    h = _token(client, "liq-6@example.com")
    cid, pid = _contribuyente(client, h)
    _fuente(client, h, cid, pid, "Salario de la empresa X", 100000000)
    _fuente(client, h, cid, pid, "Arrendamiento del local", 30000000)
    _fuente(client, h, cid, pid, "Concepto que no dice nada", 5000000)

    ingresos = client.get(f"{_base(cid, pid)}/ingresos", headers=h).json()
    por_concepto = {i["concepto"]: i for i in ingresos}

    assert por_concepto["Salario de la empresa X"]["cedula"] == "TRABAJO"
    assert por_concepto["Arrendamiento del local"]["cedula"] == "CAPITAL"
    assert por_concepto["Concepto que no dice nada"]["cedula"] == "SIN_CLASIFICAR"
    assert all(i["origen_clasificacion"] == "SUGERIDA" for i in ingresos)


def test_la_clasificacion_manual_reemplaza_la_sugerida(client):
    h = _token(client, "liq-7@example.com")
    cid, pid = _contribuyente(client, h)
    fid = _fuente(client, h, cid, pid, "Salario de la empresa X", 100000000)

    guardado = client.put(
        f"{_base(cid, pid)}/ingresos",
        json=[{"fuente_ingreso_id": fid, "cedula": "NO_LABORAL"}],
        headers=h,
    ).json()

    assert guardado[0]["cedula"] == "NO_LABORAL"
    assert guardado[0]["origen_clasificacion"] == "MANUAL"


def test_no_se_puede_clasificar_una_fuente_de_otro_contribuyente(client):
    h = _token(client, "liq-8@example.com")
    cid_a, pid_a = _contribuyente(client, h)
    cid_b, pid_b = _contribuyente(client, h)
    fid_b = _fuente(client, h, cid_b, pid_b, "Salario", 1000000)

    respuesta = client.put(
        f"{_base(cid_a, pid_a)}/ingresos",
        json=[{"fuente_ingreso_id": fid_b, "cedula": "TRABAJO"}],
        headers=h,
    )

    assert respuesta.status_code == 404


def test_el_catalogo_de_cedulas_explica_que_implica_cada_una(client):
    h = _token(client, "liq-9@example.com")
    catalogo = client.get("/liquidacion/cedulas", headers=h).json()
    valores = {c["valor"] for c in catalogo}
    assert {"TRABAJO", "TRABAJO_SIN_VINCULO", "CAPITAL", "NO_LABORAL"} <= valores
    assert all(c["implicacion"] for c in catalogo)


# ---------------------------------------------------------------------------
# Liquidación de punta a punta
# ---------------------------------------------------------------------------


def test_liquida_un_asalariado_con_deducciones_y_activos(client):
    h = _token(client, "liq-10@example.com")
    cid, pid = _contribuyente(client, h)
    _fuente(client, h, cid, pid, "Salario de la empresa X", 180000000, retencion=9500000)
    client.post(
        f"/contribuyentes/{cid}/activos",
        json={"descripcion": "Apartamento", "tipo": "INMUEBLE", "valor": 420000000,
              "periodo_fiscal_id": pid},
        headers=h,
    )
    client.patch(
        f"{_base(cid, pid)}/hoja",
        json={
            "aportes_obligatorios_salud": "7200000",
            "aportes_obligatorios_pension": "7200000",
            "numero_dependientes": 2,
            "compras_con_factura_electronica": "40000000",
            "deudas": "95000000",
        },
        headers=h,
    )
    client.post(
        f"{_base(cid, pid)}/deducciones",
        json={"nombre": "Intereses de vivienda", "valor": "12000000",
              "fuente_legal": "Art. 119 ET"},
        headers=h,
    )
    client.post(
        f"{_base(cid, pid)}/deducciones",
        json={"nombre": "Aportes voluntarios AFC", "valor": "20000000",
              "fuente_legal": "Art. 126-4 ET"},
        headers=h,
    )

    liq = client.get(_base(cid, pid), headers=h).json()

    assert liq["anio_gravable"] == 2025
    assert D(liq["parametros"]["uvt"]) == D("49799")
    assert _valor(liq, "CG-INGRESOS") == D("180000000.00")
    assert _valor(liq, "CG-INCRNGO") == D("14400000.00")
    assert _valor(liq, "CG-BASE-LIMITE") == D("165600000.00")
    # 25 % × (180.000.000 − 14.400.000 − 32.000.000) = 33.400.000
    assert _valor(liq, "CG-EXENTA-25") == D("33400000.00")
    # Solicitado 65.400.000 cabe en el 40 % (66.240.000) y en 1.340 UVT.
    assert _valor(liq, "CG-EXENTAS-LIMITADAS") == D("65400000.00")
    assert _valor(liq, "CG-RENTA-LIQUIDA") == D("92628944.00")
    assert _valor(liq, "PAT-LIQUIDO") == D("325000000.00")
    assert _valor(liq, "RETENCIONES") == D("9500000.00")
    assert _valor(liq, "SALDO-A-PAGAR") == D("0.00")
    assert _valor(liq, "SALDO-A-FAVOR") > D("0")
    assert liq["diagnosticos"] == []


def test_un_ingreso_sin_clasificar_no_entra_en_la_liquidacion_y_se_reporta(client):
    """Es la regla que evita una declaración equivocada en silencio."""
    h = _token(client, "liq-11@example.com")
    cid, pid = _contribuyente(client, h)
    _fuente(client, h, cid, pid, "Salario de la empresa X", 100000000)
    _fuente(client, h, cid, pid, "Movimiento sin descripción clara", 50000000)

    liq = client.get(_base(cid, pid), headers=h).json()

    assert _valor(liq, "CG-INGRESOS") == D("100000000.00")  # los 50.000.000 quedaron fuera
    assert [i["concepto"] for i in liq["ingresos_sin_clasificar"]] == [
        "Movimiento sin descripción clara"
    ]
    assert any("sin clasificar" in d for d in liq["diagnosticos"])


def test_al_clasificarlo_el_ingreso_entra_en_la_liquidacion(client):
    h = _token(client, "liq-12@example.com")
    cid, pid = _contribuyente(client, h)
    fid = _fuente(client, h, cid, pid, "Movimiento sin descripción clara", 50000000)
    client.put(
        f"{_base(cid, pid)}/ingresos",
        json=[{"fuente_ingreso_id": fid, "cedula": "NO_LABORAL"}],
        headers=h,
    )

    liq = client.get(_base(cid, pid), headers=h).json()

    assert _valor(liq, "CG-INGRESOS") == D("50000000.00")
    assert liq["ingresos_sin_clasificar"] == []


def test_cada_renglon_viaja_con_su_formula_su_fuente_y_su_valor_declarable(client):
    h = _token(client, "liq-13@example.com")
    cid, pid = _contribuyente(client, h)
    _fuente(client, h, cid, pid, "Salario de la empresa X", 150000000)

    liq = client.get(_base(cid, pid), headers=h).json()

    impuesto = next(r for r in liq["renglones"] if r["codigo"] == "IMP-RENTA")
    assert "UVT" in impuesto["formula"]
    assert "241" in impuesto["fuente_legal"]
    assert D(impuesto["valor_declarable"]) % D("1000") == D("0")
    assert liq["parametros"]["fuente_uvt"]
    assert "art. 581" in liq["advertencia"]


def test_un_ano_sin_parametros_devuelve_422_con_instrucciones(client):
    """El periodo existe; lo que falta son los parámetros. 422, no 404."""
    h = _token(client, "liq-14@example.com")
    cid, pid = _contribuyente(client, h, anio=2015)

    respuesta = client.get(_base(cid, pid), headers=h)

    assert respuesta.status_code == 422
    assert "tablas_oficiales.py" in respuesta.json()["detail"]


def test_la_liquidacion_se_exporta_a_excel_y_pdf(client):
    h = _token(client, "liq-15@example.com")
    cid, pid = _contribuyente(client, h)
    _fuente(client, h, cid, pid, "Salario de la empresa X", 150000000)

    xlsx = client.get(f"{_base(cid, pid)}/exportar?formato=xlsx", headers=h)
    pdf = client.get(f"{_base(cid, pid)}/exportar?formato=pdf", headers=h)

    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert "borrador_liquidacion" in xlsx.headers["content-disposition"]


# ---------------------------------------------------------------------------
# Aislamiento entre contadores y auditoría
# ---------------------------------------------------------------------------


def test_un_contador_no_alcanza_la_liquidacion_de_otro(client):
    h_a = _token(client, "liq-16a@example.com")
    h_b = _token(client, "liq-16b@example.com")
    cid, pid = _contribuyente(client, h_a)

    assert client.get(_base(cid, pid), headers=h_b).status_code == 404
    assert client.get(f"{_base(cid, pid)}/hoja", headers=h_b).status_code == 404
    assert client.patch(
        f"{_base(cid, pid)}/hoja", json={"deudas": "1"}, headers=h_b
    ).status_code == 404


def test_sin_token_no_se_liquida(client):
    h = _token(client, "liq-17@example.com")
    cid, pid = _contribuyente(client, h)
    assert client.get(_base(cid, pid)).status_code == 401


def test_las_decisiones_de_liquidacion_quedan_auditadas(client):
    h = _token(client, "liq-18@example.com")
    cid, pid = _contribuyente(client, h)
    fid = _fuente(client, h, cid, pid, "Salario", 1000000)
    client.patch(f"{_base(cid, pid)}/hoja", json={"numero_dependientes": 1}, headers=h)
    client.post(f"{_base(cid, pid)}/deducciones", json={"nombre": "X", "valor": "1"}, headers=h)
    client.put(
        f"{_base(cid, pid)}/ingresos",
        json=[{"fuente_ingreso_id": fid, "cedula": "TRABAJO"}],
        headers=h,
    )

    acciones = [e["accion"] for e in client.get("/auditoria", headers=h).json()]

    assert "actualizar_hoja" in acciones
    assert "crear_deduccion" in acciones
    assert "clasificar_ingresos" in acciones
