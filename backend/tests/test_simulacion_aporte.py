"""Simulación de un aporte voluntario a AFC o pensión voluntaria.

Responde la pregunta de planeación más común: «¿cuánto me baja el impuesto si
aporto X?». Lo que estas pruebas vigilan no es que el número baje —eso lo hace
el motor— sino que el aporte se recorte a lo que la ley deja deducir y que la
simulación no toque nada de lo guardado.
"""

from decimal import Decimal as D

from tests.test_liquidacion_api import _base, _contribuyente, _fuente, _token

SALARIO = 150_000_000


def _preparar(client, email: str):
    h = _token(client, email)
    cid, pid = _contribuyente(client, h)
    _fuente(client, h, cid, pid, "Salario", SALARIO, retencion=5_000_000)
    return h, cid, pid


def _simular(client, h, cid, pid, valor):
    return client.get(f"{_base(cid, pid)}/simulacion-aporte?valor={valor}", headers=h)


def test_un_aporte_dentro_del_cupo_baja_el_impuesto(client):
    h, cid, pid = _preparar(client, "sim-1@example.com")

    cuerpo = _simular(client, h, cid, pid, 5_000_000).json()

    assert D(cuerpo["valor_deducible"]) == 5_000_000
    assert cuerpo["recortado"] is False
    assert cuerpo["motivo_recorte"] is None
    assert D(cuerpo["ahorro_en_impuesto"]) > 0
    assert D(cuerpo["con_aporte"]["impuesto"]) < D(cuerpo["actual"]["impuesto"])


def test_el_aporte_se_recorta_a_lo_que_la_ley_deja_deducir(client):
    """Lo que hace honesto al simulador.

    Sin esto diría que aportar mil millones ahorra proporcionalmente, que es
    un consejo equivocado con apariencia de cálculo.
    """
    h, cid, pid = _preparar(client, "sim-2@example.com")

    cuerpo = _simular(client, h, cid, pid, 1_000_000_000).json()

    assert cuerpo["recortado"] is True
    assert cuerpo["motivo_recorte"] in ("LIMITE_GENERAL", "TOPE_PROPIO")
    assert D(cuerpo["valor_deducible"]) < D(cuerpo["valor_propuesto"])


def test_el_deducible_nunca_pasa_de_ninguno_de_los_dos_topes(client):
    h, cid, pid = _preparar(client, "sim-3@example.com")

    cuerpo = _simular(client, h, cid, pid, 1_000_000_000).json()

    deducible = D(cuerpo["valor_deducible"])
    assert deducible <= D(cuerpo["limite_general"]["disponible"])
    assert deducible <= D(cuerpo["tope_propio"]["disponible"])


def test_los_dos_topes_vienen_con_su_norma(client):
    """Ninguna cifra de tope está escrita en el código de la simulación."""
    h, cid, pid = _preparar(client, "sim-4@example.com")

    cuerpo = _simular(client, h, cid, pid, 1_000_000).json()

    assert "336" in cuerpo["limite_general"]["fuente_legal"]
    assert "126" in cuerpo["tope_propio"]["fuente_legal"]


def test_la_simulacion_no_guarda_nada(client):
    h, cid, pid = _preparar(client, "sim-5@example.com")
    antes = client.get(_base(cid, pid), headers=h).json()

    _simular(client, h, cid, pid, 10_000_000)

    despues = client.get(_base(cid, pid), headers=h).json()
    assert despues["renglones"] == antes["renglones"]


def test_la_simulacion_advierte_de_lo_que_no_evalua(client):
    h, cid, pid = _preparar(client, "sim-6@example.com")

    cuerpo = _simular(client, h, cid, pid, 1_000_000).json()

    texto = " ".join(cuerpo["advertencias"]).lower()
    assert "no modifica" in texto
    assert "año gravable" in texto


def test_un_aporte_de_cero_o_negativo_no_se_simula(client):
    h, cid, pid = _preparar(client, "sim-7@example.com")

    assert _simular(client, h, cid, pid, 0).status_code == 422
    assert _simular(client, h, cid, pid, -1).status_code == 422


def test_un_contador_no_simula_sobre_el_contribuyente_de_otro(client):
    h, cid, pid = _preparar(client, "sim-8@example.com")
    otro = _token(client, "sim-9@example.com")

    assert _simular(client, otro, cid, pid, 1_000_000).status_code == 404


def test_el_tope_del_30_por_ciento_del_ingreso_si_aplica(client):
    """Los arts. 126-1 y 126-4 ponen dos techos y manda el menor.

    Con un ingreso de 150 millones, el 30 % son 45 millones, muy por debajo
    de las 3.800 UVT. Si el techo que se devuelve es el de las UVT, el
    porcentaje no se está aplicando: fue lo que pasó al escribir mal el
    código del renglón de ingresos, que `valor()` resuelve como cero sin
    avisar.
    """
    h, cid, pid = _preparar(client, "sim-10@example.com")

    cuerpo = _simular(client, h, cid, pid, 1_000_000).json()

    techo = D(cuerpo["tope_propio"]["techo"])
    assert techo == D(SALARIO) * D("0.30")
