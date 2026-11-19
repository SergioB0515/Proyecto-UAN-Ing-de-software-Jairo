"""La tabla única de conciliación y el valor final que fija el contador.

Reutiliza los ayudantes de `test_portal` en vez de copiarlos: el montaje
(contador, contribuyente, periodo, enlace, exógena cargada) es el mismo.
"""

from tests.test_portal import (
    _agregar,
    _aceptar,
    _contribuyente,
    _enlace,
    _h,
    _preparar,
    _token_contador,
)

VALOR_BANCO = 14_850_000
VALOR_SALARIOS = 64_800_000


def _conciliar(client, token, contribuyente_id, periodo_id):
    return client.get(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/conciliacion",
        headers=_h(token),
    )


def _fijar(client, token, contribuyente_id, periodo_id, **datos):
    return client.put(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}"
        "/conciliacion/decisiones",
        json=datos,
        headers=_h(token),
    )


def _item(cuerpo, contiene: str):
    return next(i for i in cuerpo["items"] if contiene.lower() in i["concepto"].lower())


# ---------------------------------------------------------------------------
# La tabla
# ---------------------------------------------------------------------------


def test_cada_fila_tiene_clave_y_etiqueta_en_palabras(client):
    token, cid, pid, _ = _preparar(client, "dec-01@example.com")
    cuerpo = _conciliar(client, token, cid, pid).json()

    assert cuerpo["items"]
    for item in cuerpo["items"]:
        assert item["clave"]
        assert item["etiqueta_estado"] in {
            "Coincide", "Hay diferencia", "Solo en la exógena", "Solo en lo declarado"
        }
    # Las claves son únicas: una decisión por fila.
    claves = [i["clave"] for i in cuerpo["items"]]
    assert len(claves) == len(set(claves))


def test_los_adicionales_entran_a_la_misma_tabla(client):
    token, cid, pid, enlace = _preparar(client, "dec-02@example.com")
    _agregar(
        client, enlace["token"], tipo="MEDICINA_PREPAGADA",
        descripcion="Póliza Ejemplo", valor=2_000_000,
    )

    cuerpo = _conciliar(client, token, cid, pid).json()
    item = _item(cuerpo, "Póliza Ejemplo")
    assert item["origen"] == "Adicional"
    # La exógena nunca trae medicina prepagada: solo está en lo declarado.
    assert item["estado"] == "NO_REPORTADO_POR_TERCERO"
    assert item["valor_declarado"] == 2_000_000
    assert item["valor_exogena"] is None


def test_un_adicional_patrimonial_si_se_cruza_con_la_exogena(client):
    """Un bien declarado por el contribuyente puede estar reportado."""
    token, cid, pid, enlace = _preparar(client, "dec-03@example.com")
    _agregar(
        client, enlace["token"], tipo="ACTIVO",
        descripcion="cuentas de ahorro", valor=VALOR_BANCO,
    )

    cuerpo = _conciliar(client, token, cid, pid).json()
    item = _item(cuerpo, "cuentas de ahorro")
    assert item["estado"] == "COINCIDE"
    assert item["valor_exogena"] == VALOR_BANCO
    assert item["nombre_reportante"] == "BANCOLOMBIA S A"


def test_los_dependientes_no_entran_a_la_tabla_de_valores(client):
    """Son un número de personas, no una cifra en pesos."""
    token, cid, pid, enlace = _preparar(client, "dec-04@example.com")
    _agregar(
        client, enlace["token"], tipo="DEPENDIENTE",
        descripcion="Hijos menores", cantidad=2,
    )

    cuerpo = _conciliar(client, token, cid, pid).json()
    assert not any("Hijos menores" in i["concepto"] for i in cuerpo["items"])
    # Pero sí están en la pestaña de adicionales.
    adicionales = client.get(
        f"/contribuyentes/{cid}/periodos-fiscales/{pid}/adicionales", headers=_h(token)
    ).json()
    assert any(a["tipo"] == "DEPENDIENTE" and a["cantidad"] == 2 for a in adicionales)


# ---------------------------------------------------------------------------
# El valor final
# ---------------------------------------------------------------------------


def test_elegir_la_exogena_guarda_el_valor_de_la_exogena(client):
    token, cid, pid, _ = _preparar(client, "dec-05@example.com")
    item = _item(_conciliar(client, token, cid, pid).json(), "Saldo de cuentas")

    respuesta = _fijar(
        client, token, cid, pid,
        clave_item=item["clave"],
        fuente_elegida="EXOGENA",
        # Un valor distinto en el cuerpo: tiene que ignorarse. Si se tomara,
        # el registro diría «elegí la exógena» junto a otra cifra.
        valor_final=1,
        nota="El banco certificó este saldo",
    )
    assert respuesta.status_code == 200, respuesta.text
    decision = respuesta.json()
    assert float(decision["valor_final"]) == VALOR_BANCO
    assert decision["fuente_elegida"] == "EXOGENA"
    assert decision["nota"] == "El banco certificó este saldo"
    assert decision["decidida_por_contador_id"]


def test_la_decision_vuelve_en_la_conciliacion(client):
    token, cid, pid, _ = _preparar(client, "dec-06@example.com")
    item = _item(_conciliar(client, token, cid, pid).json(), "Pagos por salarios")
    _fijar(client, token, cid, pid, clave_item=item["clave"], fuente_elegida="EXOGENA")

    cuerpo = _conciliar(client, token, cid, pid).json()
    decidido = _item(cuerpo, "Pagos por salarios")
    assert decidido["valor_final"] == VALOR_SALARIOS
    assert decidido["fuente_valor_final"] == "EXOGENA"
    assert decidido["decidida_en"]
    assert cuerpo["total_decididos"] == 1
    assert cuerpo["total_sin_decidir"] == len(cuerpo["items"]) - 1


def test_no_se_puede_elegir_una_fuente_que_no_tiene_valor(client):
    token, cid, pid, enlace = _preparar(client, "dec-07@example.com")
    _agregar(
        client, enlace["token"], tipo="MEDICINA_PREPAGADA",
        descripcion="Póliza Ejemplo", valor=2_000_000,
    )
    cuerpo = _conciliar(client, token, cid, pid).json()

    solo_declarado = _item(cuerpo, "Póliza Ejemplo")
    respuesta = _fijar(
        client, token, cid, pid,
        clave_item=solo_declarado["clave"], fuente_elegida="EXOGENA",
    )
    assert respuesta.status_code == 422
    assert "exógena" in respuesta.json()["detail"]

    solo_exogena = _item(cuerpo, "Saldo de cuentas")
    respuesta = _fijar(
        client, token, cid, pid,
        clave_item=solo_exogena["clave"], fuente_elegida="DECLARADO",
    )
    assert respuesta.status_code == 422


def test_la_fuente_manual_exige_el_valor(client):
    token, cid, pid, _ = _preparar(client, "dec-08@example.com")
    item = _item(_conciliar(client, token, cid, pid).json(), "Saldo de cuentas")

    sin_valor = _fijar(
        client, token, cid, pid, clave_item=item["clave"], fuente_elegida="MANUAL"
    )
    assert sin_valor.status_code == 422

    con_valor = _fijar(
        client, token, cid, pid,
        clave_item=item["clave"], fuente_elegida="MANUAL", valor_final=15_000_000,
        nota="El extracto dice otra cosa",
    )
    assert con_valor.status_code == 200
    assert float(con_valor.json()["valor_final"]) == 15_000_000


def test_una_clave_que_no_esta_en_la_tabla_se_rechaza(client):
    token, cid, pid, _ = _preparar(client, "dec-09@example.com")

    respuesta = _fijar(
        client, token, cid, pid, clave_item="EXO:999999", fuente_elegida="MANUAL",
        valor_final=1000,
    )
    assert respuesta.status_code == 422


def test_la_decision_se_puede_cambiar_y_deshacer(client):
    token, cid, pid, _ = _preparar(client, "dec-10@example.com")
    item = _item(_conciliar(client, token, cid, pid).json(), "Saldo de cuentas")

    _fijar(client, token, cid, pid, clave_item=item["clave"], fuente_elegida="EXOGENA")
    _fijar(
        client, token, cid, pid, clave_item=item["clave"],
        fuente_elegida="MANUAL", valor_final=1_000_000,
    )
    decisiones = client.get(
        f"/contribuyentes/{cid}/periodos-fiscales/{pid}/conciliacion/decisiones",
        headers=_h(token),
    ).json()
    # Se actualizó en su sitio: una decisión por renglón, no un historial de
    # cifras contradictorias en la misma fila.
    assert len(decisiones) == 1
    assert decisiones[0]["fuente_elegida"] == "MANUAL"

    borrado = client.delete(
        f"/contribuyentes/{cid}/periodos-fiscales/{pid}"
        f"/conciliacion/decisiones/{item['clave']}",
        headers=_h(token),
    )
    assert borrado.status_code == 204
    assert _conciliar(client, token, cid, pid).json()["total_decididos"] == 0


def test_solo_el_contador_fija_el_valor_final(client):
    """El portal del contribuyente no tiene una ruta equivalente."""
    token, cid, pid, enlace = _preparar(client, "dec-11@example.com")
    item = _item(_conciliar(client, token, cid, pid).json(), "Saldo de cuentas")

    # Ni por su propia ruta...
    assert client.put(
        f"/carga/{enlace['token']}/conciliacion/decisiones",
        json={"clave_item": item["clave"], "fuente_elegida": "EXOGENA"},
    ).status_code in (404, 405)

    # ...ni usando el token del portal como si fuera una sesión de contador.
    assert client.put(
        f"/contribuyentes/{cid}/periodos-fiscales/{pid}/conciliacion/decisiones",
        json={"clave_item": item["clave"], "fuente_elegida": "EXOGENA"},
        headers={"Authorization": f"Bearer {enlace['token']}"},
    ).status_code == 401


def test_un_contador_no_decide_sobre_contribuyentes_de_otro(client):
    token_a, cid, pid, _ = _preparar(client, "dec-12a@example.com")
    token_b = _token_contador(client, "dec-12b@example.com")
    item = _item(_conciliar(client, token_a, cid, pid).json(), "Saldo de cuentas")

    respuesta = _fijar(
        client, token_b, cid, pid, clave_item=item["clave"], fuente_elegida="EXOGENA"
    )
    assert respuesta.status_code == 404


# ---------------------------------------------------------------------------
# El panel de cartera como pantalla de entrada
# ---------------------------------------------------------------------------


def test_la_cartera_dice_a_quien_le_falta_que(client):
    token, cid, pid, enlace = _preparar(client, "dec-13@example.com")
    documentos = client.get(f"/carga/{enlace['token']}").json()["documentos"]
    pendiente = next(d for d in documentos if d["estado"] == "PENDIENTE")
    client.patch(
        f"/carga/{enlace['token']}/documentos/{pendiente['clave']}",
        json={"estado": "NO_ENTIENDO"},
    )
    total_pendientes = len(documentos) - 1

    panel = client.get("/cartera", headers=_h(token)).json()
    fila = next(f for f in panel["contribuyentes"] if f["contribuyente_id"] == cid)

    assert fila["exogena_cargada"] is True
    assert fila["fecha_corte_exogena"]
    assert fila["enlace_vigente"] is True
    assert fila["politica_aceptada"] is True
    assert fila["documentos_no_entiendo"] == 1
    assert fila["documentos_pendientes"] == total_pendientes
    assert panel["total_no_entiendo"] == 1
    assert panel["total_soportes_pendientes"] == total_pendientes
    assert any("no entiendo" in aviso for aviso in fila["avisos"])


def test_la_cartera_avisa_cuando_no_hay_enlace_vigente(client):
    token, cid, pid, enlace = _preparar(client, "dec-14@example.com")
    client.post(
        f"/contribuyentes/{cid}/enlaces-carga/{enlace['id']}/revocar", headers=_h(token)
    )

    panel = client.get("/cartera", headers=_h(token)).json()
    fila = next(f for f in panel["contribuyentes"] if f["contribuyente_id"] == cid)
    assert fila["enlace_vigente"] is False
    assert panel["total_sin_enlace"] == 1
    assert any("enlace de carga vigente" in aviso for aviso in fila["avisos"])


def test_la_cartera_se_puede_ordenar_por_lo_que_falta(client):
    token = _token_contador(client, "dec-15@example.com")
    # Dos contribuyentes: a uno le faltan soportes, al otro no.
    con_pendientes, periodo_a = _contribuyente(client, token, rut="1000000000")
    sin_nada, _ = _contribuyente(client, token, rut="2000000001")
    enlace = _enlace(client, token, con_pendientes, periodo_a)
    _aceptar(client, enlace["token"])
    client.post(
        f"/carga/{enlace['token']}/exogena",
        files={
            "archivo": (
                "exogena.xlsx",
                __import__("tests.test_portal", fromlist=["_libro"])._libro(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    panel = client.get("/cartera?orden=pendientes", headers=_h(token)).json()
    assert panel["contribuyentes"][0]["contribuyente_id"] == con_pendientes
    assert panel["contribuyentes"][-1]["contribuyente_id"] == sin_nada
