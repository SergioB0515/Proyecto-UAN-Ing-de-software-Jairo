"""La gestión de la declaración, a través de la API.

El recorrido de una temporada: pedir documentos, registrar la declaración del
año anterior, presentar, corregir y pagar tarde.
"""

from datetime import date
from decimal import Decimal as D

import pytest

from modulos.gestion import servicios as gestion_servicios

from .test_exogena import RUTA_FIXTURE

HOY = date(2026, 12, 1)
VENCE = date(2026, 8, 20)


@pytest.fixture(autouse=True)
def _hoy_fijo(monkeypatch):
    monkeypatch.setattr(gestion_servicios, "_hoy", lambda: HOY)


def _token(client, email):
    client.post("/contadores/registro", json={
        "nombre": "Contadora Prueba", "email": email, "contrasena": "claveDePrueba1"})
    login = client.post("/contadores/login",
                        data={"username": email, "password": "claveDePrueba1"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _contribuyente(client, h, rut="1000000777", anio=2025, salario=180_000_000):
    cid = client.post("/contribuyentes", json={
        "nombre": "MARIA FERNANDA LOPEZ", "rut": rut,
        "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": anio}, headers=h).json()["id"]
    client.patch(f"/contribuyentes/{cid}/periodos-fiscales/{pid}",
                 json={"fecha_vencimiento_manual": VENCE.isoformat()}, headers=h)
    client.post(f"/contribuyentes/{cid}/fuentes-ingreso", json={
        "concepto": "Salario", "valor_anual": salario, "retencion_fuente": 0,
        "periodo_fiscal_id": pid}, headers=h)
    return cid, pid


def _b(cid, pid):
    return f"/contribuyentes/{cid}/periodos-fiscales/{pid}"


def _gestion(client, h, cid, pid, **params):
    r = client.get(f"{_b(cid, pid)}/gestion", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _etapa(g, clave):
    return next(e for e in g["proceso"]["etapas"] if e["clave"] == clave)


# --- Etapas -----------------------------------------------------------------


def test_una_declaracion_nueva_empieza_por_la_exogena(client):
    h = _token(client, "gestion-a@example.com")
    cid, pid = _contribuyente(client, h)
    g = _gestion(client, h, cid, pid)
    assert g["proceso"]["etapa_actual"] == "EXOGENA"
    assert g["proceso"]["total"] == 7
    assert g["vencimiento"] == VENCE.isoformat()
    assert g["firmeza"]["fecha"] is None


def test_las_etapas_de_criterio_las_marca_el_contador(client):
    h = _token(client, "gestion-b@example.com")
    cid, pid = _contribuyente(client, h)
    r = client.patch(f"{_b(cid, pid)}/gestion/seguimiento", headers=h, json={
        "cruce_revisado_en": "2026-08-01", "liquidacion_revisada_en": "2026-08-02"})
    assert r.status_code == 200
    g = r.json()
    assert _etapa(g, "CRUCE")["hecha"] and _etapa(g, "LIQUIDACION")["hecha"]
    assert _etapa(g, "APROBACION")["hecha"] is False


# --- Documentos -------------------------------------------------------------


def _subir_exogena(client, h, cid, pid):
    with open(RUTA_FIXTURE, "rb") as f:
        r = client.post(f"{_b(cid, pid)}/exogena", headers=h, files={
            "archivo": ("exogena.xlsx", f, "application/octet-stream")})
    assert r.status_code == 201, r.text


def test_la_solicitud_de_documentos_sale_de_la_exogena(client):
    h = _token(client, "gestion-c@example.com")
    cid, pid = _contribuyente(client, h)
    _subir_exogena(client, h, cid, pid)

    sol = client.get(f"{_b(cid, pid)}/documentos", headers=h).json()
    claves = {d["clave"] for d in sol["documentos"]}
    assert "DECLARACION_ANTERIOR" in claves
    assert any(c.startswith("PREDIAL") for c in claves)
    assert sol["pendientes"] == len(sol["documentos"])
    assert "Hola, Maria:" in sol["mensaje"]
    assert "año gravable 2025" in sol["mensaje"]

    clave = sol["documentos"][0]["clave"]
    sol = client.patch(f"{_b(cid, pid)}/documentos/{clave}", headers=h,
                       json={"estado": "RECIBIDO"}).json()
    recibido = next(d for d in sol["documentos"] if d["clave"] == clave)
    assert recibido["estado"] == "RECIBIDO" and recibido["actualizado_en"] == HOY.isoformat()
    assert sol["recibidos"] == 1

    sol = client.post(f"{_b(cid, pid)}/documentos", headers=h, json={
        "descripcion": "Certificado de la cooperativa", "tercero": "COOPERATIVA X"}).json()
    assert any(d["manual"] and d["tercero"] == "COOPERATIVA X" for d in sol["documentos"])


def test_marcar_todos_los_documentos_completa_la_etapa(client):
    h = _token(client, "gestion-d@example.com")
    cid, pid = _contribuyente(client, h)
    sol = client.get(f"{_b(cid, pid)}/documentos", headers=h).json()
    for d in sol["documentos"]:
        client.patch(f"{_b(cid, pid)}/documentos/{d['clave']}", headers=h,
                     json={"estado": "NO_APLICA"})
    assert _etapa(_gestion(client, h, cid, pid), "DOCUMENTOS")["hecha"] is True


def test_un_documento_que_no_existe_da_404(client):
    h = _token(client, "gestion-e@example.com")
    cid, pid = _contribuyente(client, h)
    r = client.patch(f"{_b(cid, pid)}/documentos/NO_EXISTE:1", headers=h,
                     json={"estado": "RECIBIDO"})
    assert r.status_code == 404


# --- Presentación y corrección ----------------------------------------------


def test_presentar_guarda_la_declaracion_y_fija_la_fecha(client):
    h = _token(client, "gestion-f@example.com")
    cid, pid = _contribuyente(client, h)
    r = client.post(f"{_b(cid, pid)}/gestion/presentaciones", headers=h,
                    json={"fecha_presentacion": "2026-08-10", "numero_formulario": "2101234"})
    assert r.status_code == 201, r.text
    decl = r.json()
    assert decl["es_correccion"] is False
    assert D(decl["casillas"]["32"]) == D("180000000")

    g = _gestion(client, h, cid, pid)
    assert g["fecha_presentacion"] == "2026-08-10"
    assert _etapa(g, "PRESENTADA")["hecha"]
    assert g["firmeza"]["fecha"] == "2029-08-20"
    assert g["correccion"] is None


def test_un_cambio_despues_de_presentar_es_una_correccion_con_sancion(client):
    h = _token(client, "gestion-g@example.com")
    cid, pid = _contribuyente(client, h)
    client.post(f"{_b(cid, pid)}/gestion/presentaciones", headers=h,
                json={"fecha_presentacion": "2026-08-10"})
    antes = _gestion(client, h, cid, pid)["saldo_a_pagar"]

    # Aparece un ingreso que no se había declarado.
    client.post(f"/contribuyentes/{cid}/fuentes-ingreso", headers=h, json={
        "concepto": "Bonificación", "valor_anual": 60_000_000, "retencion_fuente": 0,
        "periodo_fiscal_id": pid})
    g = _gestion(client, h, cid, pid)
    corr = g["correccion"]
    assert corr["tipo"] == "AUMENTA"
    assert D(corr["mayor_valor"]) > 0
    assert D(corr["sancion"]) == max(
        (D(corr["mayor_valor"]) * D("0.10")).quantize(D("1")), D("10") * D("52374"))
    assert corr["plazo"] == "2029-08-20"
    # Las tasas publicadas llegan hasta octubre de 2026; noviembre y el 1 de
    # diciembre (el «hoy» de la prueba) no se inventan: se reportan.
    assert corr["intereses"]["meses_sin_tasa"] == ["2026-11", "2026-12"]
    assert [t["desde"][:7] for t in corr["intereses"]["tramos"]] == [
        "2026-08", "2026-09", "2026-10"]
    # Lo vigente sigue siendo lo presentado hasta que se registre la corrección.
    assert g["saldo_a_pagar"] == antes

    r = client.post(f"{_b(cid, pid)}/gestion/presentaciones", headers=h,
                    json={"fecha_presentacion": "2026-12-01"})
    assert r.json()["es_correccion"] is True
    g = _gestion(client, h, cid, pid)
    assert g["correccion"] is None
    assert g["fecha_presentacion"] == "2026-08-10"     # la inicial manda
    assert len(g["presentaciones"]) == 2


def test_una_correccion_no_puede_ser_anterior_a_la_ultima(client):
    h = _token(client, "gestion-h@example.com")
    cid, pid = _contribuyente(client, h)
    client.post(f"{_b(cid, pid)}/gestion/presentaciones", headers=h,
                json={"fecha_presentacion": "2026-08-10"})
    r = client.post(f"{_b(cid, pid)}/gestion/presentaciones", headers=h,
                    json={"fecha_presentacion": "2026-08-01"})
    assert r.status_code == 422


# --- Año anterior, comparativo y beneficio de auditoría ----------------------


def test_la_declaracion_anterior_alimenta_comparativo_beneficio_y_hoja(client):
    h = _token(client, "gestion-i@example.com")
    cid, pid = _contribuyente(client, h)
    r = client.post(f"/contribuyentes/{cid}/declaraciones-anteriores", headers=h, json={
        "anio_gravable": 2024, "fecha_presentacion": "2025-08-15",
        "casillas": {"29": 150_000_000, "31": 140_000_000, "32": 120_000_000,
                     "126": 4_000_000, "133": 1_500_000, "137": 0}})
    assert r.status_code == 201, r.text

    g = _gestion(client, h, cid, pid)
    assert g["declaracion_anterior"]["anio_gravable"] == 2024
    comp = g["comparativo"]
    assert comp["origen_anterior"] == "Registrada a mano"
    fila_32 = next(f for f in comp["filas"] if f["casilla"] == 32)
    assert D(fila_32["anterior"]) == D("120000000") and fila_32["revisar"] is True
    anticipo = next(c for c in comp["coherencias"] if "130" in c["descripcion"])
    assert anticipo["cuadra"] is False and D(anticipo["esperado"]) == D("1500000")
    assert g["beneficio_auditoria"]["impuesto_anterior"] is not None
    assert D(g["beneficio_auditoria"]["impuesto_para_6_meses"]) == D("5400000")

    cambios = client.post(f"{_b(cid, pid)}/gestion/traer-del-anio-anterior",
                          headers=h).json()
    assert any("casilla 133" in c for c in cambios)
    g = _gestion(client, h, cid, pid)
    anticipo = next(c for c in g["comparativo"]["coherencias"] if "130" in c["descripcion"])
    assert anticipo["cuadra"] is True

    # El año anterior quedó como periodo cerrado, no como un año en trabajo.
    periodos = client.get(f"/contribuyentes/{cid}/periodos-fiscales", headers=h).json()
    assert next(p for p in periodos if p["anio_gravable"] == 2024)["estado"] == "CERRADO"


def test_la_declaracion_anterior_rechaza_casillas_inexistentes(client):
    h = _token(client, "gestion-j@example.com")
    cid, _ = _contribuyente(client, h)
    r = client.post(f"/contribuyentes/{cid}/declaraciones-anteriores", headers=h, json={
        "anio_gravable": 2024, "fecha_presentacion": "2025-08-15",
        "casillas": {"999": 1}})
    assert r.status_code == 422


def test_traer_del_anio_anterior_sin_declaracion_da_422(client):
    h = _token(client, "gestion-k@example.com")
    cid, pid = _contribuyente(client, h)
    assert client.post(f"{_b(cid, pid)}/gestion/traer-del-anio-anterior",
                       headers=h).status_code == 422


# --- Intereses de mora ------------------------------------------------------


def test_pagar_tarde_genera_intereses_con_las_tasas_de_la_dian(client):
    h = _token(client, "gestion-l@example.com")
    cid, pid = _contribuyente(client, h)
    # Las tasas publicadas por la DIAN vienen con la app: no hay que cargarlas.
    tasas = client.get("/tasas-interes-moratorio", headers=h).json()
    assert {(t["anio"], t["mes"]) for t in tasas} >= {(2026, 8), (2026, 9)}

    # Año anterior con 4 M de impuesto: este año lo supera de sobra.
    client.post(f"/contribuyentes/{cid}/declaraciones-anteriores", headers=h, json={
        "anio_gravable": 2024, "fecha_presentacion": "2025-08-15",
        "casillas": {"126": 4_000_000}})
    client.post(f"{_b(cid, pid)}/gestion/presentaciones", headers=h,
                json={"fecha_presentacion": "2026-08-10"})
    g = client.patch(f"{_b(cid, pid)}/gestion/seguimiento", headers=h,
                     json={"pagada_en": "2026-09-30"}).json()
    i = g["intereses"]
    assert i["pagado"] is True and i["dias"] == 41
    assert [t["dias"] for t in i["tramos"]] == [11, 30]
    capital = D(i["capital"])
    esperado = (capital * D("0.2766") / 365 * 11 + capital * D("0.2724") / 365 * 30)
    assert D(i["valor"]) == esperado.quantize(D("1"))
    assert _etapa(g, "PAGO")["hecha"]
    # Pagó tarde: pierde el beneficio de auditoría aunque lo alcanzara.
    pago = next(c for c in g["beneficio_auditoria"]["condiciones"]
                if "Pagada" in c["descripcion"])
    assert pago["cumple"] is False
    assert g["beneficio_auditoria"]["meses"] is None
    assert g["firmeza"]["fecha"] == "2029-08-20"


def test_una_tasa_editada_reemplaza_la_publicada(client):
    h = _token(client, "gestion-m@example.com")
    client.put("/tasas-interes-moratorio", headers=h, json={
        "anio": 2026, "mes": 8, "tasa_efectiva_anual": "30.00", "fuente": "Prueba"})
    tasas = client.get("/tasas-interes-moratorio", headers=h).json()
    agosto = next(t for t in tasas if (t["anio"], t["mes"]) == (2026, 8))
    assert D(str(agosto["tasa_efectiva_anual"])) == D("30")


# --- Informe, cartera y aislamiento -----------------------------------------


def test_el_informe_para_el_cliente_es_un_pdf(client):
    h = _token(client, "gestion-n@example.com")
    cid, pid = _contribuyente(client, h)
    r = client.get(f"{_b(cid, pid)}/informe-cliente", headers=h)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    assert "informe_renta_1000000777_2025.pdf" in r.headers["content-disposition"]

    from io import BytesIO
    from pypdf import PdfReader
    texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)
    assert "Su declaración de renta del año gravable 2025" in texto
    assert "20 de agosto de 2026" in texto


def test_la_cartera_muestra_la_etapa_de_cada_cliente(client):
    h = _token(client, "gestion-o@example.com")
    cid, pid = _contribuyente(client, h)
    fila = next(f for f in client.get("/cartera", headers=h).json()["contribuyentes"]
                if f["contribuyente_id"] == cid)
    assert fila["etapa_actual"] == "EXOGENA"
    assert fila["etapa_nombre"] == "Cargar la exógena"
    assert fila["etapas_total"] == 7
    assert fila["documentos_pendientes"] >= 1


def test_otro_contador_no_ve_la_gestion(client):
    h = _token(client, "gestion-p1@example.com")
    otro = _token(client, "gestion-p2@example.com")
    cid, pid = _contribuyente(client, h)
    assert client.get(f"{_b(cid, pid)}/gestion", headers=otro).status_code == 404
    assert client.get(f"{_b(cid, pid)}/documentos", headers=otro).status_code == 404
    assert client.get(f"{_b(cid, pid)}/informe-cliente", headers=otro).status_code == 404
    assert client.post(f"/contribuyentes/{cid}/declaraciones-anteriores", headers=otro,
                       json={"anio_gravable": 2024, "fecha_presentacion": "2025-08-15",
                             "casillas": {}}).status_code == 404


def test_pagar_a_tiempo_con_incremento_suficiente_acorta_la_firmeza(client):
    h = _token(client, "gestion-q@example.com")
    cid, pid = _contribuyente(client, h)
    client.post(f"/contribuyentes/{cid}/declaraciones-anteriores", headers=h, json={
        "anio_gravable": 2024, "fecha_presentacion": "2025-08-15",
        "casillas": {"126": 4_000_000}})
    client.post(f"{_b(cid, pid)}/gestion/presentaciones", headers=h,
                json={"fecha_presentacion": "2026-08-10"})
    g = client.patch(f"{_b(cid, pid)}/gestion/seguimiento", headers=h,
                     json={"pagada_en": "2026-08-12"}).json()
    assert g["beneficio_auditoria"]["meses"] == 6
    assert g["firmeza"]["fecha"] == "2027-02-10"
    assert "689-3" in g["firmeza"]["fuente"]
    assert g["intereses"] is None


def test_la_liquidacion_usa_el_patrimonio_liquido_declarado_el_ano_anterior(client):
    h = _token(client, "gestion-r@example.com")
    cid, pid = _contribuyente(client, h)
    client.post(f"/contribuyentes/{cid}/declaraciones-anteriores", headers=h, json={
        "anio_gravable": 2024, "fecha_presentacion": "2025-08-15",
        "casillas": {"31": 10_000_000}})
    # Un activo de 400 M este año contra 10 M declarados: la comparación
    # patrimonial tiene que partir de lo declarado.
    client.post(f"/contribuyentes/{cid}/activos", headers=h, json={
        "descripcion": "Apartamento", "tipo": "INMUEBLE", "valor": 400_000_000,
        "periodo_fiscal_id": pid})
    liq = client.get(f"/liquidacion{_b(cid, pid)}", headers=h).json()
    comparacion = next(r for r in liq["renglones"] if r["codigo"] == "COMP-PATRIMONIAL")
    # 400 M de hoy − 10 M declarados el año anterior.
    assert "incremento $390.000.000" in comparacion["formula"]


def test_el_informe_de_una_declaracion_vencida_no_dice_que_aun_hay_plazo(client):
    h = _token(client, "gestion-s@example.com")
    cid, pid = _contribuyente(client, h)      # vence el 20 de agosto; hoy es 1 de dic.
    from io import BytesIO
    from pypdf import PdfReader
    r = client.get(f"{_b(cid, pid)}/informe-cliente", headers=h)
    texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)
    texto = " ".join(texto.split())
    assert "venció el 20 de agosto de 2026" in texto
    assert "Fecha límite" not in texto


def test_el_informe_menciona_cada_ingreso_reportado_que_no_se_declaro(client):
    h = _token(client, "gestion-t@example.com")
    cid, pid = _contribuyente(client, h)
    _subir_exogena(client, h, cid, pid)
    conc = client.get(f"{_b(cid, pid)}/conciliacion", headers=h).json()
    no_declarados = [i for i in conc["items"] if i["estado"] == "NO_DECLARADO"]
    assert no_declarados
    from io import BytesIO
    from pypdf import PdfReader
    r = client.get(f"{_b(cid, pid)}/informe-cliente", headers=h)
    texto = " ".join(" ".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages).split())
    assert "no está en la declaración" in texto
    assert "cubre lo que bancos" not in texto
