"""La IP que se registra no la puede elegir el cliente.

Antes el contenedor arrancaba uvicorn con `--forwarded-allow-ips='*'`, y con
eso `request.client.host` era la primera entrada de `X-Forwarded-For`: la que
escribe quien hace la petición. La bitácora, los intentos de acceso y el
respaldo de la autorización del portal guardaban lo que el cliente quisiera.
"""

import pathlib

import pytest
from sqlmodel import select
from starlette.requests import Request

from core import config
from core.red import ip_cliente
from modulos.auditoria.modelos import IntentoAcceso
from modulos.portal.modelos import AutorizacionTratamiento

from .test_portal import CONSULTANTE, _contribuyente, _enlace, _token_contador

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FALSA = "1.2.3.4"
REAL = "203.0.113.9"


def _peticion(*cabeceras: str, conexion: str = "10.0.0.7") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", valor.encode()) for valor in cabeceras],
            "client": (conexion, 50000),
        }
    )


@pytest.fixture()
def proxies(monkeypatch):
    def fijar(numero: int) -> None:
        monkeypatch.setattr(config, "PROXIES_CONFIABLES", numero)

    return fijar


# --- La regla ---------------------------------------------------------------


def test_sin_proxies_la_cabecera_no_se_lee(proxies):
    proxies(0)
    assert ip_cliente(_peticion(f"{FALSA}, {REAL}")) == "10.0.0.7"


def test_con_un_proxy_manda_la_entrada_que_el_proxy_agrego(proxies):
    proxies(1)
    assert ip_cliente(_peticion(f"{FALSA}, {REAL}")) == REAL


def test_con_un_proxy_y_sin_cabecera_falsa(proxies):
    proxies(1)
    assert ip_cliente(_peticion(REAL)) == REAL


def test_con_dos_proxies_se_cuenta_desde_la_derecha(proxies):
    proxies(2)
    assert ip_cliente(_peticion(f"{FALSA}, {REAL}, 10.9.9.9")) == REAL


def test_cabecera_repetida_se_lee_en_orden(proxies):
    proxies(1)
    assert ip_cliente(_peticion(FALSA, REAL)) == REAL


def test_menos_entradas_que_proxies_registra_la_conexion(proxies):
    proxies(2)
    assert ip_cliente(_peticion(REAL)) == "10.0.0.7"


def test_sin_cabecera_registra_la_conexion(proxies):
    proxies(1)
    assert ip_cliente(_peticion()) == "10.0.0.7"


def test_una_entrada_que_no_es_ip_no_se_registra(proxies):
    proxies(1)
    assert ip_cliente(_peticion(f"{REAL}, <script>")) == "10.0.0.7"


def test_ipv6(proxies):
    proxies(1)
    assert ip_cliente(_peticion(f"{FALSA}, 2001:db8::1")) == "2001:db8::1"


def test_valor_invalido_de_la_variable_detiene_el_arranque(monkeypatch):
    monkeypatch.setenv("PROXIES_CONFIABLES", "-1")
    with pytest.raises(RuntimeError, match="PROXIES_CONFIABLES"):
        config._entero_no_negativo("PROXIES_CONFIABLES", "0")


# --- Donde se usa -----------------------------------------------------------


def _ips_de_intentos(session, email: str) -> set:
    return set(session.exec(select(IntentoAcceso.ip).where(IntentoAcceso.email == email)).all())


def test_login_fallido_no_registra_la_ip_inventada(client, session, proxies):
    proxies(0)
    client.post(
        "/contadores/login",
        data={"username": "red-1@example.com", "password": "claveMala999"},
        headers={"X-Forwarded-For": FALSA},
    )
    assert FALSA not in _ips_de_intentos(session, "red-1@example.com")


def test_login_detras_del_proxy_registra_la_ip_real(client, session, proxies):
    proxies(1)
    client.post(
        "/contadores/login",
        data={"username": "red-2@example.com", "password": "claveMala999"},
        headers={"X-Forwarded-For": f"{FALSA}, {REAL}"},
    )
    assert _ips_de_intentos(session, "red-2@example.com") == {REAL}


def test_la_autorizacion_del_portal_se_respalda_con_la_red_real(client, session, proxies):
    token = _token_contador(client, "red-3@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)
    enlace = _enlace(client, token, contribuyente_id, periodo_id)

    proxies(1)
    version = client.get(f"/carga/{enlace['token']}").json()["politica"]["version"]
    respuesta = client.post(
        f"/carga/{enlace['token']}/politica",
        json={
            "version_politica": version,
            "nombre_quien_acepta": "Contribuyente Ejemplo",
            "documento_quien_acepta": CONSULTANTE,
            "acepto": True,
        },
        headers={"X-Forwarded-For": f"{FALSA}, {REAL}"},
    )
    assert respuesta.status_code == 201, respuesta.text

    autorizacion = session.exec(
        select(AutorizacionTratamiento).where(
            AutorizacionTratamiento.contribuyente_id == contribuyente_id
        )
    ).one()
    assert autorizacion.red_origen == "203.0.113.0/24"


# --- El despliegue ----------------------------------------------------------


def test_el_contenedor_no_le_delega_la_confianza_a_uvicorn():
    """Si la bandera vuelve, uvicorn reescribe la IP antes de que llegue aquí
    y todo lo de arriba deja de importar."""
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    comando = next(linea for linea in dockerfile.splitlines() if linea.startswith("CMD"))
    assert "forwarded-allow-ips" not in comando
    assert "--no-proxy-headers" in comando
