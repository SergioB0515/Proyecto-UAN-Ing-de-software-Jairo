from datetime import date, timedelta

import pytest

from modulos.parametros.calendario_oficial import CALENDARIOS_OFICIALES
from modulos.parametros.modelos import EstadoVencimiento
from modulos.parametros.servicios import calcular_vencimiento, cargar_calendario_oficial, ultimos_dos_digitos


def _headers(client, email: str) -> dict:
    client.post("/contadores/registro", json={"nombre": "Contadora", "email": email, "contrasena": "claveSegura123"})
    token = client.post("/contadores/login", data={"username": email, "password": "claveSegura123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _contribuyente(client, h, nombre: str, rut: str, anio: int = 2025):
    cid = client.post("/contribuyentes", json={"nombre": nombre, "rut": rut, "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales", json={"anio_gravable": anio}, headers=h).json()["id"]
    return cid, pid


@pytest.mark.parametrize(
    "rut, esperado",
    [("79845123", 23), ("79845100", 100), ("900123456-7", 56), ("1.020.304.050", 50), ("7", None), ("", None)],
)
def test_ultimos_dos_digitos(rut, esperado):
    assert ultimos_dos_digitos(rut) == esperado


def test_el_calendario_oficial_cubre_todos_los_digitos():
    tramos = CALENDARIOS_OFICIALES[2025]
    cubiertos = [d for desde, hasta, _ in tramos for d in range(desde, hasta + 1)]
    assert cubiertos == list(range(1, 101))
    fechas = [fecha for _, _, fecha in tramos]
    assert fechas == sorted(fechas)
    assert (fechas[0], fechas[-1]) == (date(2026, 8, 12), date(2026, 10, 26))


def test_cargar_calendario_oficial_por_api(client):
    h = _headers(client, "venc-1@example.com")
    cargado = client.post("/parametros/plazos/2025/calendario-oficial", headers=h)
    no_disponible = client.post("/parametros/plazos/2031/calendario-oficial", headers=h)

    assert cargado.status_code == 200
    assert len(cargado.json()) == 50
    assert len(client.get("/parametros/plazos/2025", headers=h).json()) == 50
    assert no_disponible.status_code == 404


def test_calendario_con_rangos_solapados_falla(client):
    h = _headers(client, "venc-2@example.com")
    solapado = [
        {"digitos_desde": 1, "digitos_hasta": 10, "fecha": "2027-08-10"},
        {"digitos_desde": 10, "digitos_hasta": 20, "fecha": "2027-08-11"},
    ]
    invertido = [{"digitos_desde": 9, "digitos_hasta": 3, "fecha": "2027-08-10"}]
    assert client.put("/parametros/plazos/2026", json=solapado, headers=h).status_code == 422
    assert client.put("/parametros/plazos/2026", json=invertido, headers=h).status_code == 422


def test_reemplazar_calendario_borra_el_anterior(client):
    h = _headers(client, "venc-3@example.com")
    client.post("/parametros/plazos/2025/calendario-oficial", headers=h)
    nuevo = [{"digitos_desde": 1, "digitos_hasta": 100, "fecha": "2026-09-30"}]
    assert len(client.put("/parametros/plazos/2025", json=nuevo, headers=h).json()) == 1


def test_estados_del_vencimiento(session):
    cargar_calendario_oficial(session, 2025)
    def estado(hoy, presentada=None, manual=None):
        return calcular_vencimiento(session, "79845123", 2025, manual, presentada, hoy=hoy)

    assert estado(date(2026, 6, 1)).estado == EstadoVencimiento.PENDIENTE
    assert estado(date(2026, 8, 20)).estado == EstadoVencimiento.PROXIMA
    assert estado(date(2026, 8, 20)).dias_restantes == 8
    assert estado(date(2026, 8, 29)).estado == EstadoVencimiento.VENCIDA
    assert estado(date(2026, 8, 29), presentada=date(2026, 8, 15)).estado == EstadoVencimiento.PRESENTADA

    manual = estado(date(2026, 8, 29), manual=date(2026, 11, 30))
    assert (manual.fecha, manual.origen, manual.estado) == (date(2026, 11, 30), "MANUAL", EstadoVencimiento.PENDIENTE)
    assert estado(date(2026, 6, 1)).origen == "CALENDARIO"
    assert estado(date(2026, 6, 1)).ultimos_digitos == "23"


def test_sin_calendario_queda_sin_fecha(session):
    assert calcular_vencimiento(session, "79845123", 2019, None, None).estado == EstadoVencimiento.SIN_FECHA


def test_registrar_presentacion_y_fecha_manual(client):
    h = _headers(client, "venc-4@example.com")
    client.post("/parametros/plazos/2025/calendario-oficial", headers=h)
    cid, pid = _contribuyente(client, h, "Ana", "79845123")
    url = f"/contribuyentes/{cid}/periodos-fiscales/{pid}"

    manual = (date.today() + timedelta(days=40)).isoformat()
    r = client.patch(url, json={"fecha_vencimiento_manual": manual}, headers=h)
    assert r.status_code == 200
    venc = client.get(f"{url}/resumen", headers=h).json()["vencimiento"]
    assert (venc["fecha"], venc["origen"], venc["estado"]) == (manual, "MANUAL", "PENDIENTE")

    client.patch(url, json={"fecha_presentacion": date.today().isoformat()}, headers=h)
    assert client.get(f"{url}/resumen", headers=h).json()["vencimiento"]["estado"] == "PRESENTADA"

    client.patch(url, json={"fecha_vencimiento_manual": None}, headers=h)
    assert client.get(f"{url}/resumen", headers=h).json()["vencimiento"]["fecha"] == "2026-08-28"


def test_se_registra_la_presentacion_aunque_el_periodo_este_cerrado(client):
    h = _headers(client, "venc-5@example.com")
    cid, pid = _contribuyente(client, h, "Ana", "79845123")
    client.post(f"/contribuyentes/{cid}/periodos-fiscales/{pid}/cerrar", headers=h)
    r = client.patch(f"/contribuyentes/{cid}/periodos-fiscales/{pid}", json={"fecha_presentacion": "2026-08-20"}, headers=h)
    assert r.status_code == 200
    assert r.json()["fecha_presentacion"] == "2026-08-20"


def test_otro_contador_no_actualiza_el_periodo(client):
    h = _headers(client, "venc-6a@example.com")
    otro = _headers(client, "venc-6b@example.com")
    cid, pid = _contribuyente(client, h, "Ana", "79845123")
    r = client.patch(f"/contribuyentes/{cid}/periodos-fiscales/{pid}", json={"fecha_presentacion": "2026-08-20"}, headers=otro)
    assert r.status_code == 404


def test_cartera_ordenada_por_vencimiento(client):
    h = _headers(client, "venc-7@example.com")
    client.post("/parametros/plazos/2025/calendario-oficial", headers=h)
    _contribuyente(client, h, "Vence en octubre", "1020304099")
    _contribuyente(client, h, "Vence en agosto", "79845101")
    cid, pid = _contribuyente(client, h, "Ya presentó", "79845102")
    client.patch(f"/contribuyentes/{cid}/periodos-fiscales/{pid}", json={"fecha_presentacion": "2026-08-01"}, headers=h)
    _contribuyente(client, h, "Sin periodo 2025", "79845150", anio=2024)

    cuerpo = client.get("/cartera?anio_gravable=2025&orden=vencimiento", headers=h).json()

    nombres = [f["nombre"] for f in cuerpo["contribuyentes"]]
    assert nombres == ["Vence en agosto", "Vence en octubre", "Sin periodo 2025", "Ya presentó"]
    filas = {f["nombre"]: f for f in cuerpo["contribuyentes"]}
    assert filas["Vence en agosto"]["vencimiento"]["fecha"] == "2026-08-12"
    assert filas["Ya presentó"]["vencimiento"]["estado"] == "PRESENTADA"
    assert filas["Sin periodo 2025"]["vencimiento"] is None


@pytest.mark.parametrize("formato, tipo", [("xlsx", "spreadsheetml"), ("pdf", "pdf")])
def test_exportar_cartera(client, formato, tipo):
    h = _headers(client, f"venc-8-{formato}@example.com")
    _contribuyente(client, h, "Ana", "79845123")

    r = client.get(f"/cartera/exportar?formato={formato}", headers=h)

    assert r.status_code == 200
    assert tipo in r.headers["content-type"]
    assert r.headers["content-disposition"].startswith('attachment; filename="cartera_')
    assert len(r.content) > 500
    eventos = client.get("/auditoria", headers=h).json()
    assert eventos[0]["descripcion"] == f"Exportó el panel de cartera ({formato})"
