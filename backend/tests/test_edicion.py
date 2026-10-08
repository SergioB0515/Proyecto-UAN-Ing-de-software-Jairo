"""Edición y eliminación de contribuyentes, activos y fuentes de ingreso
(corrección de errores de digitación)."""


def _crear_contador_y_token(client, email: str) -> str:
    client.post(
        "/contadores/registro",
        json={"nombre": "Contador", "email": email, "contrasena": "clave-segura-1"},
    )
    respuesta = client.post(
        "/contadores/login", data={"username": email, "password": "clave-segura-1"}
    )
    return respuesta.json()["access_token"]


class Escenario:
    def __init__(self, client, email: str, tipo: str = "MIXTO", con_periodo: bool = True):
        self.client = client
        self.h = {"Authorization": f"Bearer {_crear_contador_y_token(client, email)}"}
        self.cid = client.post(
            "/contribuyentes",
            json={"nombre": "Ana Pérez", "rut": "1010", "tipo_contribuyente": tipo},
            headers=self.h,
        ).json()["id"]
        self.pid = None
        if con_periodo:
            self.pid = client.post(
                f"/contribuyentes/{self.cid}/periodos-fiscales",
                json={"anio_gravable": 2025},
                headers=self.h,
            ).json()["id"]

    def url(self, sufijo: str = "") -> str:
        return f"/contribuyentes/{self.cid}{sufijo}"

    def activo(self, **extra) -> dict:
        datos = {"descripcion": "Cuenta", "tipo": "CUENTA", "valor": 1000,
                 "periodo_fiscal_id": self.pid, **extra}
        return self.client.post(self.url("/activos"), json=datos, headers=self.h).json()

    def fuente(self, **extra) -> dict:
        datos = {"concepto": "Salario", "valor_anual": 5000, "periodo_fiscal_id": self.pid, **extra}
        return self.client.post(self.url("/fuentes-ingreso"), json=datos, headers=self.h).json()


# ------------------------------------------------------------- Contribuyente


def test_editar_contribuyente(client):
    e = Escenario(client, "ed-1@example.com", con_periodo=False)
    r = client.patch(e.url(), json={"nombre": "Ana María Pérez", "rut": "2020"}, headers=e.h)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Ana María Pérez"
    assert r.json()["rut"] == "2020"
    assert r.json()["tipo_contribuyente"] == "MIXTO"  # lo no enviado no cambia


def test_no_pasa_a_asalariado_con_inventario(client):
    e = Escenario(client, "ed-2@example.com", con_periodo=False)
    client.post(e.url("/categorias"), json={"nombre": "Granos"}, headers=e.h)
    r = client.patch(e.url(), json={"tipo_contribuyente": "ASALARIADO"}, headers=e.h)
    assert r.status_code == 409


def test_pasa_a_asalariado_sin_inventario(client):
    e = Escenario(client, "ed-3@example.com", con_periodo=False)
    r = client.patch(e.url(), json={"tipo_contribuyente": "ASALARIADO"}, headers=e.h)
    assert r.status_code == 200


def test_eliminar_contribuyente_sin_datos(client):
    e = Escenario(client, "ed-4@example.com", con_periodo=False)
    assert client.delete(e.url(), headers=e.h).status_code == 204
    assert client.get(e.url(), headers=e.h).status_code == 404


def test_no_se_elimina_contribuyente_con_periodos(client):
    e = Escenario(client, "ed-5@example.com")
    assert client.delete(e.url(), headers=e.h).status_code == 409


def test_otro_contador_no_edita_ni_elimina(client):
    e = Escenario(client, "ed-6a@example.com", con_periodo=False)
    otro = {"Authorization": f"Bearer {_crear_contador_y_token(client, 'ed-6b@example.com')}"}
    assert client.patch(e.url(), json={"nombre": "X"}, headers=otro).status_code == 404
    assert client.delete(e.url(), headers=otro).status_code == 404


# -------------------------------------------------------------------- Activos


def test_editar_activo_y_borrar_vinculo(client):
    e = Escenario(client, "ed-7@example.com")
    activo = e.activo(vinculo_codigo_concepto="1476")

    r = client.patch(
        e.url(f"/activos/{activo['id']}"),
        json={"valor": 2500, "vinculo_codigo_concepto": ""},
        headers=e.h,
    )

    assert r.status_code == 200
    assert r.json()["valor"] == 2500
    assert r.json()["vinculo_codigo_concepto"] is None
    assert r.json()["descripcion"] == "Cuenta"
    patrimonio = client.get(e.url("/patrimonio"), headers=e.h).json()["patrimonio_liquido"]
    assert patrimonio == 2500


def test_editar_activo_con_valor_invalido_falla(client):
    e = Escenario(client, "ed-8@example.com")
    activo = e.activo()
    r = client.patch(e.url(f"/activos/{activo['id']}"), json={"valor": 0}, headers=e.h)
    assert r.status_code == 422


def test_eliminar_activo(client):
    e = Escenario(client, "ed-9@example.com")
    activo = e.activo()
    assert client.delete(e.url(f"/activos/{activo['id']}"), headers=e.h).status_code == 204
    assert client.get(e.url("/activos"), headers=e.h).json() == []


def test_no_se_edita_activo_de_periodo_cerrado(client):
    e = Escenario(client, "ed-10@example.com", tipo="ASALARIADO")
    activo = e.activo()
    client.post(e.url(f"/periodos-fiscales/{e.pid}/cerrar"), headers=e.h)

    assert client.patch(e.url(f"/activos/{activo['id']}"), json={"valor": 1}, headers=e.h).status_code == 409
    assert client.delete(e.url(f"/activos/{activo['id']}"), headers=e.h).status_code == 409


def test_no_se_edita_el_inventario_del_cierre(client):
    e = Escenario(client, "ed-11@example.com")
    cierre = client.post(e.url(f"/periodos-fiscales/{e.pid}/cerrar"), headers=e.h).json()
    # Aunque se reabra el periodo, el inventario lo borra la reapertura;
    # mientras está cerrado, no se toca a mano.
    activo_id = cierre["activo_inventario_id"]
    assert client.delete(e.url(f"/activos/{activo_id}"), headers=e.h).status_code == 409


def test_activo_de_otro_contribuyente_no_se_encuentra(client):
    e = Escenario(client, "ed-12@example.com")
    activo = e.activo()
    otro_cid = client.post(
        "/contribuyentes",
        json={"nombre": "Otro", "rut": "3030", "tipo_contribuyente": "ASALARIADO"},
        headers=e.h,
    ).json()["id"]
    r = client.delete(f"/contribuyentes/{otro_cid}/activos/{activo['id']}", headers=e.h)
    assert r.status_code == 404


def test_no_se_cambia_un_activo_a_inventario(client):
    e = Escenario(client, "ed-13@example.com")
    activo = e.activo()
    r = client.patch(e.url(f"/activos/{activo['id']}"), json={"tipo": "INVENTARIO"}, headers=e.h)
    assert r.status_code == 422


# ----------------------------------------------------------- Fuentes de ingreso


def test_editar_y_eliminar_fuente_de_ingreso(client):
    e = Escenario(client, "ed-14@example.com")
    fuente = e.fuente()

    r = client.patch(
        e.url(f"/fuentes-ingreso/{fuente['id']}"),
        json={"valor_anual": 7000, "retencion_fuente": 300},
        headers=e.h,
    )
    assert r.status_code == 200
    assert (r.json()["valor_anual"], r.json()["retencion_fuente"]) == (7000, 300)

    assert client.delete(e.url(f"/fuentes-ingreso/{fuente['id']}"), headers=e.h).status_code == 204
    assert client.get(e.url("/fuentes-ingreso"), headers=e.h).json() == []


def test_no_se_edita_fuente_de_periodo_cerrado(client):
    e = Escenario(client, "ed-15@example.com", tipo="ASALARIADO")
    fuente = e.fuente()
    client.post(e.url(f"/periodos-fiscales/{e.pid}/cerrar"), headers=e.h)
    r = client.patch(e.url(f"/fuentes-ingreso/{fuente['id']}"), json={"valor_anual": 1}, headers=e.h)
    assert r.status_code == 409
