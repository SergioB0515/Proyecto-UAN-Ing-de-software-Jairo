"""Pruebas de conciliación (HU-08, HU-09) y borrador de renglones (HU-10)
contra el fixture de exógena — ver tests/fixtures/reporte_exogena_ejemplo.xlsx.

Registros del fixture relevantes aquí:
- Avalúo catastral (1476) ........ 120.000.000  R29
- Venta en notaría (1032) ......... 50.000.000  R112
- Movimientos en cuentas .......... 3.000.000
- CDT (1020) ...................... 8.000.000
- Impuestos y gravámenes (2204) ...... 50.000  R29
- Retención en notaría (1032) ....... 450.000  R132  (excluida)
- Consumos con tarjeta (1023) ....... 500.000        (excluida)
- Facturación DIAN y dos autoreportados          (excluidos)
"""
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


def _preparar(client, email: str, importar: bool = True) -> tuple:
    token = _crear_contador_y_token(client, email)
    contribuyente_id = client.post(
        "/contribuyentes",
        json={"nombre": "Contribuyente Ejemplo", "rut": "1000000000", "tipo_contribuyente": "MIXTO"},
        headers=_headers(token),
    ).json()["id"]
    periodo_id = client.post(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales",
        json={"anio_gravable": 2025},
        headers=_headers(token),
    ).json()["id"]
    if importar:
        with open(RUTA_FIXTURE, "rb") as archivo:
            client.post(
                f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/exogena",
                files={"archivo": ("exogena.xlsx", archivo, "application/octet-stream")},
                headers=_headers(token),
            )
    return token, contribuyente_id, periodo_id


def _registrar(client, token, contribuyente_id, ruta, datos):
    respuesta = client.post(
        f"/contribuyentes/{contribuyente_id}/{ruta}", json=datos, headers=_headers(token)
    )
    assert respuesta.status_code == 201


def _conciliar(client, token, contribuyente_id, periodo_id):
    return client.get(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/conciliacion",
        headers=_headers(token),
    )


def test_conciliacion_clasifica_cada_item(client):
    token, cid, pid = _preparar(client, "conc-1@example.com")
    _registrar(client, token, cid, "activos", {
        "descripcion": "Apartamento", "tipo": "INMUEBLE", "valor": 120000000,
        "vinculo_codigo_concepto": "1476",
    })
    _registrar(client, token, cid, "activos", {
        "descripcion": "Cuenta de ahorros", "tipo": "CUENTA", "valor": 3500000,
        "vinculo_palabra_clave": "movimientos en cuentas",
    })
    _registrar(client, token, cid, "activos", {
        "descripcion": "Moto", "tipo": "VEHICULO", "valor": 8000000,
    })
    _registrar(client, token, cid, "fuentes-ingreso", {
        "concepto": "Venta apartamento", "valor_anual": 50000000, "vinculo_codigo_concepto": "1032",
    })

    respuesta = _conciliar(client, token, cid, pid)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    estados = {i["concepto"]: i for i in cuerpo["items"]}
    assert estados["Apartamento"]["estado"] == "COINCIDE"
    assert estados["Venta apartamento"]["estado"] == "COINCIDE"
    assert estados["Cuenta de ahorros"]["estado"] == "DISCREPANCIA"
    assert estados["Cuenta de ahorros"]["diferencia"] == -500000
    assert estados["Moto"]["estado"] == "NO_REPORTADO_POR_TERCERO"

    no_declarados = [i for i in cuerpo["items"] if i["estado"] == "NO_DECLARADO"]
    codigos = sorted(i["concepto_code"] for i in no_declarados)
    # CDT e impuestos; nunca retención, tarjeta, DIAN ni autoreportados.
    assert codigos == ["1020", "2204"]
    assert cuerpo["resumen"] == {
        "COINCIDE": 2,
        "DISCREPANCIA": 1,
        "NO_DECLARADO": 2,
        "NO_REPORTADO_POR_TERCERO": 1,
    }


def test_la_retencion_no_se_cruza_con_un_ingreso(client):
    # La retención de notaría comparte el código 1032 con el ingreso. Una
    # segunda fuente con ese código no debe cruzarse contra la retención.
    token, cid, pid = _preparar(client, "conc-2@example.com")
    for concepto, valor in [("Venta apartamento", 50000000), ("Venta local", 450000)]:
        _registrar(client, token, cid, "fuentes-ingreso", {
            "concepto": concepto, "valor_anual": valor, "vinculo_codigo_concepto": "1032",
        })

    cuerpo = _conciliar(client, token, cid, pid).json()
    estados = {i["concepto"]: i["estado"] for i in cuerpo["items"]}
    assert estados["Venta apartamento"] == "COINCIDE"
    assert estados["Venta local"] == "NO_REPORTADO_POR_TERCERO"


def test_sin_datos_declarados_todo_lo_relevante_queda_no_declarado(client):
    token, cid, pid = _preparar(client, "conc-3@example.com")
    cuerpo = _conciliar(client, token, cid, pid).json()
    # Venta, avalúo, movimientos en cuentas, CDT e impuestos.
    assert cuerpo["resumen"]["NO_DECLARADO"] == 5
    assert len(cuerpo["items"]) == 5


def test_conciliar_sin_exogena_importada_falla(client):
    token, cid, pid = _preparar(client, "conc-4@example.com", importar=False)
    assert _conciliar(client, token, cid, pid).status_code == 404


def test_un_contador_no_concilia_contribuyentes_de_otro(client):
    _, cid, pid = _preparar(client, "conc-5a@example.com")
    token_b = _crear_contador_y_token(client, "conc-5b@example.com")
    assert _conciliar(client, token_b, cid, pid).status_code == 404


def test_borrador_suma_por_renglon(client):
    token, cid, pid = _preparar(client, "conc-6@example.com")

    respuesta = client.get(
        f"/contribuyentes/{cid}/periodos-fiscales/{pid}/borrador-renglones",
        headers=_headers(token),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    renglones = {r["renglon"]: r for r in cuerpo["renglones"]}
    assert renglones["R29"]["valor_total"] == 120050000
    assert renglones["R29"]["cantidad_registros"] == 2
    assert renglones["R112"]["valor_total"] == 50000000
    assert renglones["R132"]["valor_total"] == 450000
    # Ordenados por número de renglón, no alfabéticamente.
    assert [r["renglon"] for r in cuerpo["renglones"]] == ["R29", "R112", "R131", "R132"]
    assert "sugerencia" in cuerpo["advertencia"] or "editable" in cuerpo["advertencia"]


def test_borrador_sin_exogena_importada_falla(client):
    token, cid, pid = _preparar(client, "conc-7@example.com", importar=False)
    respuesta = client.get(
        f"/contribuyentes/{cid}/periodos-fiscales/{pid}/borrador-renglones",
        headers=_headers(token),
    )
    assert respuesta.status_code == 404
