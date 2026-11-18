"""Venta de inmuebles: costo fiscal, plazo de dos años y exención de vivienda."""

from datetime import date
from decimal import Decimal as D

from modulos.liquidacion.venta_inmuebles import VentaInmueble, calcular
from modulos.parametros.reajuste_activos import factor_art_73

UVT_2025 = D("49799")


def _venta(**kw):
    base = dict(descripcion="Apartamento", tipo="URBANO",
                fecha_adquisicion=date(2010, 5, 1), fecha_venta=date(2025, 6, 1),
                valor_venta=D("500000000"), costo_adquisicion=D("120000000"))
    base.update(kw)
    return VentaInmueble(**base)


# --- Tabla del art. 73 (Decreto 0449 de 2026) -------------------------------


def test_factores_contrastados_contra_dos_publicaciones_del_decreto():
    assert factor_art_73(2025, "URBANO", 1986) == D("443.02")
    assert factor_art_73(2025, "URBANO", 2010) == D("3.12")
    assert factor_art_73(2025, "URBANO", 2020) == D("1.22")
    assert factor_art_73(2025, "URBANO", 2024) == D("1.05")
    assert factor_art_73(2025, "RURAL_AGROPECUARIO", 1986) == D("429.25")
    assert factor_art_73(2025, "RURAL", 1986) == D("437.46")


def test_lo_comprado_en_1955_o_antes_usa_la_primera_fila():
    assert factor_art_73(2025, "URBANO", 1940) == factor_art_73(2025, "URBANO", 1955)


def test_lo_comprado_en_el_mismo_ano_no_se_reajusta():
    assert factor_art_73(2025, "URBANO", 2025) == D("1")


def test_sin_tabla_para_el_ano_no_inventa_factor():
    assert factor_art_73(2026, "URBANO", 2010) is None


# --- Costo fiscal (arts. 69, 72, 73) ----------------------------------------


def test_costo_reajustado_con_la_tabla_mas_mejoras():
    r = calcular(_venta(mejoras_y_valorizacion=D("10000000")), 2025, UVT_2025)
    assert r.costo_fiscal == D("384400000")        # 120 M × 3,12 + 10 M
    assert r.metodo_costo == "ART_73"
    assert r.utilidad == D("115600000")


def test_si_el_avaluo_catastral_es_mayor_se_usa_el_avaluo():
    r = calcular(_venta(avaluo_catastral_anterior=D("420000000")), 2025, UVT_2025)
    assert r.costo_fiscal == D("420000000")
    assert r.metodo_costo == "ART_72"
    assert r.utilidad == D("80000000")


def test_sin_tabla_usa_el_factor_que_escriba_el_contador_o_avisa():
    sin = calcular(_venta(fecha_venta=date(2026, 3, 1)), 2026, UVT_2025)
    assert sin.costo_fiscal == D("120000000")
    assert any("No hay tabla del art. 73" in a for a in sin.avisos)
    con = calcular(_venta(fecha_venta=date(2026, 3, 1), factor_manual=D("3.30")), 2026, UVT_2025)
    assert con.costo_fiscal == D("396000000")


# --- Plazo de dos años (art. 300) -------------------------------------------


def test_dos_anos_o_mas_es_ganancia_ocasional():
    r = calcular(_venta(fecha_adquisicion=date(2023, 6, 1), fecha_venta=date(2025, 6, 1)),
                 2025, UVT_2025)
    assert r.es_ganancia_ocasional is True


def test_menos_de_dos_anos_es_renta_ordinaria():
    r = calcular(_venta(fecha_adquisicion=date(2023, 6, 2), fecha_venta=date(2025, 6, 1)),
                 2025, UVT_2025)
    assert r.es_ganancia_ocasional is False
    assert any("menos de dos años" in a for a in r.avisos)


# --- Exención de casa de habitación (art. 311-1) ------------------------------


def test_la_casa_de_habitacion_exime_hasta_5000_uvt():
    r = calcular(_venta(valor_venta=D("900000000"), es_casa_de_habitacion=True),
                 2025, UVT_2025)
    assert r.utilidad == D("525600000")            # 900 M − 374,4 M
    assert r.exenta == D("248995000")              # 5.000 × 49.799


def test_la_exencion_se_reparte_por_participacion():
    r = calcular(_venta(valor_venta=D("900000000"), es_casa_de_habitacion=True,
                        porcentaje_participacion=D("50")), 2025, UVT_2025)
    assert r.exenta == D("124497500")
    assert "50 % de participación" in " ".join(r.avisos)


def test_si_no_es_su_vivienda_no_hay_exencion():
    assert calcular(_venta(), 2025, UVT_2025).exenta == D("0")


def test_vender_por_menos_del_costo_es_perdida_sin_utilidad():
    r = calcular(_venta(valor_venta=D("300000000")), 2025, UVT_2025)
    assert r.utilidad == D("0") and r.perdida == D("74400000")


# --- API: de la venta a las casillas del 210 --------------------------------


def _token(client, email):
    client.post("/contadores/registro", json={
        "nombre": "Contadora", "email": email, "contrasena": "claveDePrueba1"})
    login = client.post("/contadores/login",
                        data={"username": email, "password": "claveDePrueba1"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _periodo(client, h, rut="1000000888"):
    cid = client.post("/contribuyentes", json={
        "nombre": "Vendedor", "rut": rut, "tipo_contribuyente": "ASALARIADO"},
        headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]
    return cid, pid


def _b(cid, pid):
    return f"/liquidacion/contribuyentes/{cid}/periodos-fiscales/{pid}"


def _casillas(liq):
    return {r["casilla"]: D(r["valor"]) for r in liq["renglones"] if r["casilla"]}


VENTA = {"descripcion": "Apartamento Chapinero", "tipo": "URBANO",
         "fecha_adquisicion": "2010-05-01", "fecha_venta": "2025-06-01",
         "valor_venta": 900_000_000, "costo_adquisicion": 120_000_000,
         "es_casa_de_habitacion": True, "retencion": 9_000_000}


def test_la_venta_llega_a_las_casillas_de_ganancia_ocasional(client):
    h = _token(client, "venta-a@example.com")
    cid, pid = _periodo(client, h)
    r = client.post(f"{_b(cid, pid)}/ventas-inmuebles", headers=h, json=VENTA)
    assert r.status_code == 201, r.text
    venta = r.json()
    assert venta["es_ganancia_ocasional"] is True
    assert D(venta["costo_fiscal"]) == D("374400000")
    assert D(venta["exenta"]) == D("248995000")

    c = _casillas(client.get(_b(cid, pid), headers=h).json())
    assert c[112] == D("900000000")
    assert c[113] == D("374400000")
    assert c[114] == D("248995000")
    assert c[115] == D("276605000")                # 900 − 374,4 − 249,0
    assert c[127] == D("41490750")                 # 15 % de 276.605.000
    assert c[132] >= D("9000000")                  # la retención de la notaría


def test_una_venta_de_menos_de_dos_anos_va_a_rentas_no_laborales(client):
    h = _token(client, "venta-b@example.com")
    cid, pid = _periodo(client, h)
    client.post(f"{_b(cid, pid)}/ventas-inmuebles", headers=h, json={
        **VENTA, "fecha_adquisicion": "2024-02-01", "es_casa_de_habitacion": False})
    c = _casillas(client.get(_b(cid, pid), headers=h).json())
    assert c[74] == D("900000000")
    assert c[77] == D("126000000")                 # 120 M × 1,05
    assert 112 not in c


def test_la_venta_debe_ser_del_ano_que_se_declara(client):
    h = _token(client, "venta-c@example.com")
    cid, pid = _periodo(client, h)
    r = client.post(f"{_b(cid, pid)}/ventas-inmuebles", headers=h,
                    json={**VENTA, "fecha_venta": "2026-02-01"})
    assert r.status_code == 422


def test_listar_y_eliminar_ventas(client):
    h = _token(client, "venta-d@example.com")
    cid, pid = _periodo(client, h)
    vid = client.post(f"{_b(cid, pid)}/ventas-inmuebles", headers=h, json=VENTA).json()["id"]
    assert len(client.get(f"{_b(cid, pid)}/ventas-inmuebles", headers=h).json()) == 1
    assert client.delete(f"{_b(cid, pid)}/ventas-inmuebles/{vid}", headers=h).status_code == 204
    assert client.get(f"{_b(cid, pid)}/ventas-inmuebles", headers=h).json() == []
    assert client.delete(f"{_b(cid, pid)}/ventas-inmuebles/{vid}", headers=h).status_code == 404


def test_otro_contador_no_ve_ni_registra_ventas(client):
    h = _token(client, "venta-e1@example.com")
    otro = _token(client, "venta-e2@example.com")
    cid, pid = _periodo(client, h)
    assert client.get(f"{_b(cid, pid)}/ventas-inmuebles", headers=otro).status_code == 404
    assert client.post(f"{_b(cid, pid)}/ventas-inmuebles", headers=otro,
                       json=VENTA).status_code == 404


def _exogena_con_venta_en_notaria(valor):
    import io

    import openpyxl
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["NIT", "Nombre / Razón Social", "NIT", "Nombre", "Detalle", "Valor", "Uso", "Info"])
    hoja.append([899999007, "NOTARIA 20 DE BOGOTA", 1, "X",
                 "Ingreso por venta de bienes a través de notarias  (enajenante principal) "
                 "(Concepto: 1032)", valor, "R112 Ingresos por ganancias ocasionales", None])
    hoja.append([899999007, "NOTARIA 20 DE BOGOTA", 1, "X",
                 "Adquisición de bienes o derechos reportados en Notarías (adquirente "
                 "secundario) (Concepto: 1032)", 50_000_000, None, None])
    buffer = io.BytesIO()
    libro.save(buffer)
    buffer.seek(0)
    return buffer


def test_la_venta_registrada_cruza_con_lo_que_reporto_la_notaria(client):
    h = _token(client, "venta-f@example.com")
    cid, pid = _periodo(client, h)
    r = client.post(f"/contribuyentes/{cid}/periodos-fiscales/{pid}/exogena", headers=h,
                    files={"archivo": ("exo.xlsx", _exogena_con_venta_en_notaria(900_000_000),
                                       "application/octet-stream")})
    assert r.status_code == 201, r.text

    def estado_de_la_venta():
        conc = client.get(f"/contribuyentes/{cid}/periodos-fiscales/{pid}/conciliacion",
                          headers=h).json()
        return [(i["origen"], i["estado"]) for i in conc["items"] if "venta" in i["concepto"].lower()]

    assert ("Exógena", "NO_DECLARADO") in estado_de_la_venta()
    client.post(f"{_b(cid, pid)}/ventas-inmuebles", headers=h, json=VENTA)
    # La venta empareja con el registro del enajenante, no con la compra.
    assert estado_de_la_venta() == [("VentaInmueble", "COINCIDE")]
