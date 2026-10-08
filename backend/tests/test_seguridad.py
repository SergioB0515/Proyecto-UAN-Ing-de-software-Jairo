"""Incremento 6: bloqueo por intentos fallidos, política y cambio de
contraseña, auditoría de acciones, validación del archivo de exógena y
cabeceras de seguridad."""
import os
from datetime import datetime, timedelta, timezone

from fastapi.routing import APIRoute

from main import app
from modulos.auditoria.middleware import ACCIONES_AUDITADAS
from modulos.auditoria.modelos import IntentoAcceso, ResultadoAcceso

RUTA_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "reporte_exogena_ejemplo.xlsx")
CLAVE = "claveSegura123"


def _registrar(client, email: str, clave: str = CLAVE):
    return client.post(
        "/contadores/registro", json={"nombre": "Contador", "email": email, "contrasena": clave}
    )


def _login(client, email: str, clave: str = CLAVE):
    return client.post("/contadores/login", data={"username": email, "password": clave})


def _headers(client, email: str) -> dict:
    _registrar(client, email)
    return {"Authorization": f"Bearer {_login(client, email).json()['access_token']}"}


# ------------------------------------------------------- Bloqueo por fuerza bruta


def test_cinco_fallos_bloquean_aunque_la_clave_sea_correcta(client):
    _registrar(client, "seg-1@example.com")
    for _ in range(5):
        assert _login(client, "seg-1@example.com", "claveMala999").status_code == 401

    respuesta = _login(client, "seg-1@example.com")

    assert respuesta.status_code == 429
    assert int(respuesta.headers["Retry-After"]) > 0
    assert "minuto" in respuesta.json()["detail"]


def test_cuatro_fallos_no_bloquean(client):
    _registrar(client, "seg-2@example.com")
    for _ in range(4):
        _login(client, "seg-2@example.com", "claveMala999")
    assert _login(client, "seg-2@example.com").status_code == 200


def test_un_acceso_exitoso_reinicia_el_conteo(client):
    _registrar(client, "seg-3@example.com")
    for _ in range(4):
        _login(client, "seg-3@example.com", "claveMala999")
    assert _login(client, "seg-3@example.com").status_code == 200
    for _ in range(4):
        _login(client, "seg-3@example.com", "claveMala999")
    assert _login(client, "seg-3@example.com").status_code == 200


def test_los_fallos_viejos_no_cuentan(client, session):
    _registrar(client, "seg-4@example.com")
    hace_20_min = datetime.now(timezone.utc) - timedelta(minutes=20)
    for _ in range(5):
        session.add(IntentoAcceso(email="seg-4@example.com", resultado=ResultadoAcceso.FALLIDO, fecha=hace_20_min))
    session.commit()
    assert _login(client, "seg-4@example.com").status_code == 200


def test_el_bloqueo_aplica_a_emails_inexistentes(client):
    # Si solo se bloquearan cuentas reales, el 429 revelaría qué emails existen.
    for _ in range(5):
        _login(client, "nadie@example.com", "claveMala999")
    assert _login(client, "nadie@example.com", "claveMala999").status_code == 429


def test_los_intentos_durante_el_bloqueo_no_lo_extienden(client, session):
    _registrar(client, "seg-5@example.com")
    for _ in range(5):
        _login(client, "seg-5@example.com", "claveMala999")
    for _ in range(3):
        _login(client, "seg-5@example.com", "claveMala999")  # bloqueados
    resultados = [
        i.resultado
        for i in session.exec(
            IntentoAcceso.__table__.select().where(IntentoAcceso.email == "seg-5@example.com")
        ).all()
    ]
    assert resultados.count(ResultadoAcceso.FALLIDO) == 5
    assert resultados.count(ResultadoAcceso.BLOQUEADO) == 3


def test_el_contador_ve_sus_accesos(client):
    h = _headers(client, "seg-6@example.com")
    _login(client, "seg-6@example.com", "claveMala999")

    accesos = client.get("/auditoria/accesos", headers=h).json()

    assert [a["resultado"] for a in accesos[:2]] == ["FALLIDO", "EXITOSO"]
    assert accesos[0]["ip"]


# ------------------------------------------------------------------ Contraseña


def test_politica_de_contrasena(client):
    assert _registrar(client, "seg-7@example.com", "solotexto").status_code == 422
    assert _registrar(client, "seg-7@example.com", "12345678").status_code == 422
    assert _registrar(client, "seg-7@example.com", "abc123").status_code == 422
    assert _registrar(client, "seg-7@example.com", "abcd1234").status_code == 201


def test_cambiar_contrasena(client):
    h = _headers(client, "seg-8@example.com")

    mala = client.put("/contadores/yo/contrasena", json={"contrasena_actual": "otra123x", "contrasena_nueva": "nuevaClave456"}, headers=h)
    debil = client.put("/contadores/yo/contrasena", json={"contrasena_actual": CLAVE, "contrasena_nueva": "corta"}, headers=h)
    buena = client.put("/contadores/yo/contrasena", json={"contrasena_actual": CLAVE, "contrasena_nueva": "nuevaClave456"}, headers=h)

    assert mala.status_code == 400
    assert debil.status_code == 422
    assert buena.status_code == 204
    assert _login(client, "seg-8@example.com", "nuevaClave456").status_code == 200
    assert _login(client, "seg-8@example.com").status_code == 401


# ------------------------------------------------------------------- Auditoría


def test_las_acciones_quedan_auditadas(client):
    h = _headers(client, "seg-9@example.com")
    cid = client.post(
        "/contribuyentes", json={"nombre": "Ana", "rut": "1", "tipo_contribuyente": "ASALARIADO"}, headers=h
    ).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales", json={"anio_gravable": 2025}, headers=h).json()["id"]
    # Una acción fallida (422) no se audita.
    client.post(f"/contribuyentes/{cid}/activos", json={"descripcion": "X", "tipo": "CUENTA", "valor": -1, "periodo_fiscal_id": pid}, headers=h)
    client.get(f"/contribuyentes/{cid}/periodos-fiscales/{pid}/reportes/resumen?formato=pdf", headers=h)

    eventos = client.get("/auditoria", headers=h).json()

    assert [e["accion"] for e in eventos] == ["descargar_reporte", "crear_periodo_fiscal", "crear"]
    assert eventos[0]["descripcion"] == "Descargó un reporte (resumen, pdf)"
    assert eventos[0]["nombre_contribuyente"] == "Ana"
    assert all(e["contribuyente_id"] == cid for e in eventos)
    assert client.get(f"/auditoria?contribuyente_id={cid + 1}", headers=h).json() == []


def test_cada_contador_ve_solo_su_auditoria(client):
    h_a = _headers(client, "seg-10a@example.com")
    h_b = _headers(client, "seg-10b@example.com")
    client.post("/contribuyentes", json={"nombre": "De A", "rut": "1", "tipo_contribuyente": "ASALARIADO"}, headers=h_a)
    assert client.get("/auditoria", headers=h_b).json() == []


def _rutas(rutas):
    for ruta in rutas:
        if isinstance(ruta, APIRoute):
            yield ruta
        elif hasattr(ruta, "original_router"):
            yield from _rutas(ruta.original_router.routes)
        elif hasattr(ruta, "routes"):
            yield from _rutas(ruta.routes)


def test_todo_endpoint_que_modifica_esta_auditado():
    """Si se agrega un endpoint que modifica datos y no se registra en
    ACCIONES_AUDITADAS, esta prueba falla."""
    exentos = {"registro", "login"}  # quedan en el registro de accesos
    sin_auditar = [
        f"{sorted(r.methods)} {r.path} ({r.name})"
        for r in _rutas(app.router.routes)
        if r.methods & {"POST", "PUT", "PATCH", "DELETE"}
        and r.name not in ACCIONES_AUDITADAS
        and r.name not in exentos
    ]
    assert sin_auditar == []


# ---------------------------------------------------- Archivo y cabeceras HTTP


def _contribuyente_con_periodo(client, email):
    h = _headers(client, email)
    cid = client.post("/contribuyentes", json={"nombre": "A", "rut": "1", "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales", json={"anio_gravable": 2025}, headers=h).json()["id"]
    return h, f"/contribuyentes/{cid}/periodos-fiscales/{pid}/exogena"


def test_archivo_que_no_es_excel_se_rechaza_aunque_diga_xlsx(client):
    h, url = _contribuyente_con_periodo(client, "seg-11@example.com")
    falso = client.post(url, files={"archivo": ("exogena.xlsx", b"<html>no soy excel</html>")}, headers=h)
    extension = client.post(url, files={"archivo": ("exogena.csv", open(RUTA_FIXTURE, "rb").read())}, headers=h)
    assert falso.status_code == 422
    assert extension.status_code == 422


def test_archivo_demasiado_grande_se_rechaza(client, monkeypatch):
    import modulos.exogena.servicios as servicios_exogena

    monkeypatch.setattr(servicios_exogena, "TAMANO_MAXIMO_EXOGENA_MB", 0.001)  # ~1 KB
    h, url = _contribuyente_con_periodo(client, "seg-12@example.com")
    with open(RUTA_FIXTURE, "rb") as archivo:
        respuesta = client.post(url, files={"archivo": ("exogena.xlsx", archivo)}, headers=h)
    assert respuesta.status_code == 413


def test_cabeceras_de_seguridad(client):
    respuesta = client.get("/salud")
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert respuesta.headers["X-Frame-Options"] == "DENY"
