"""Pruebas del portal de carga del contribuyente.

Lo que se verifica aquí, además de que las rutas respondan:

* el alcance del enlace (un contribuyente, un periodo, revocable, reanudable);
* que el token no se pueda recuperar después de generarlo;
* que sin aceptar la política no se escriba nada;
* que ninguna fila de la exógena se descarte, ni las que no se reconocen;
* que volver a cargar el archivo no borre el trabajo del contribuyente;
* que los topes del formulario de adicionales salgan de la tabla del año.
"""

import io
from datetime import datetime, timedelta, timezone

import openpyxl
import pytest
from sqlmodel import select

from modulos.portal.modelos import EnlaceCarga

ANIO = 2025

# UVT 2025 = 49.799 (tablas_oficiales). Los topes se calculan a partir de ahí
# y NO se escriben a mano aquí: si la tabla cambia, la prueba sigue valiendo.
from modulos.parametros.tablas_oficiales import PARAMETROS_POR_ANIO  # noqa: E402

UVT = PARAMETROS_POR_ANIO[ANIO].uvt
TOPE_VIVIENDA = int(UVT * 1200)
TOPE_PREVISIONAL = int(UVT * 3800)
MAX_DEPENDIENTES = PARAMETROS_POR_ANIO[ANIO].max_dependientes

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

CONSULTANTE = "1000000000"

# (nit, nombre, detalle, valor, uso sugerido)
FILAS = [
    ("890903938", "BANCOLOMBIA S A",
     "Saldo de cuentas de ahorro y corrientes a 31 de diciembre (Concepto: 1110)",
     14_850_000, "Tope 2: Patrimonio | R29 Patrimonio Bruto"),
    ("860006555", "CLINICA DEL COUNTRY S A",
     "Pagos por salarios (Concepto: 5001)", 64_800_000,
     "Tope 1: Ingresos brutos | R32 Rentas de trabajo"),
    ("901555444", "ENTIDAD RARA LTDA",
     "Zarandeo trimestral de cosas (Concepto: 9999)", 1_200_000, None),
    (CONSULTANTE, "CONTRIBUYENTE EJEMPLO",
     "Total patrimonio bruto declarado en el año anterior", 120_000_000, None),
]


def _libro(fecha_corte: str = f"{ANIO + 1}-03-14 00:00:00", anio: int = ANIO) -> bytes:
    """Un Excel con la estructura del reporte de terceros de la DIAN."""
    libro = openpyxl.Workbook()
    hoja = libro.active

    def fila(valores):
        hoja.append(list(valores) + [None] * (8 - len(valores)))

    fila([None, None, "Consulta de Información reportada por terceros"])
    fila(["ADVERTENCIA: información a la fecha de corte del proceso."])
    fila(["Fecha corte del proceso: ", None, fecha_corte])
    fila(["Año al que se refiere la consulta:", None, str(anio)])
    fila(["Identificación del consultante"])
    fila(["Tipo de documento:", None, "C. C."])
    fila(["Identificación:", None, CONSULTANTE])
    fila(["Nombres / Razón social:", None, "CONTRIBUYENTE EJEMPLO"])
    fila([])
    fila(["NIT", "Nombre / Razón Social", "NIT",
          "Nombre/Razón Social reportada por el tercero", "Detalle", "Valor",
          "Uso declaración Sugerida", "Información  Adicional "])
    fila([None, None, None, None, "Tope 2 - Patrimonio", 134_850_000])
    for nit, nombre, detalle, valor, uso in FILAS:
        fila([nit, nombre, CONSULTANTE, "CONTRIBUYENTE EJEMPLO", detalle, valor, uso, None])

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _token_contador(client, email: str) -> str:
    client.post(
        "/contadores/registro",
        json={"nombre": "Contador de prueba", "email": email, "contrasena": "claveDePrueba1"},
    )
    login = client.post(
        "/contadores/login", data={"username": email, "password": "claveDePrueba1"}
    )
    return login.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _contribuyente(client, token: str, rut: str = CONSULTANTE) -> tuple:
    contribuyente = client.post(
        "/contribuyentes",
        json={"nombre": "Contribuyente Ejemplo", "rut": rut, "tipo_contribuyente": "MIXTO"},
        headers=_h(token),
    ).json()
    periodo = client.post(
        f"/contribuyentes/{contribuyente['id']}/periodos-fiscales",
        json={"anio_gravable": ANIO},
        headers=_h(token),
    ).json()
    return contribuyente["id"], periodo["id"]


def _enlace(client, token: str, contribuyente_id: int, periodo_id: int, dias: int = 30):
    respuesta = client.post(
        f"/contribuyentes/{contribuyente_id}/enlaces-carga",
        json={"periodo_fiscal_id": periodo_id, "dias_vigencia": dias},
        headers=_h(token),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _aceptar(client, portal_token: str):
    version = client.get(f"/carga/{portal_token}").json()["politica"]["version"]
    return client.post(
        f"/carga/{portal_token}/politica",
        json={
            "version_politica": version,
            "nombre_quien_acepta": "Contribuyente Ejemplo",
            "documento_quien_acepta": CONSULTANTE,
            "acepto": True,
        },
    )


def _cargar(client, portal_token: str, contenido: bytes = None):
    return client.post(
        f"/carga/{portal_token}/exogena",
        files={"archivo": ("exogena.xlsx", contenido or _libro(), XLSX)},
    )


def _preparar(client, email: str, cargar: bool = True) -> tuple:
    """Contador + contribuyente + enlace, con la política ya aceptada."""
    token = _token_contador(client, email)
    contribuyente_id, periodo_id = _contribuyente(client, token)
    enlace = _enlace(client, token, contribuyente_id, periodo_id)
    assert _aceptar(client, enlace["token"]).status_code == 201
    if cargar:
        assert _cargar(client, enlace["token"]).status_code == 201
    return token, contribuyente_id, periodo_id, enlace


# ---------------------------------------------------------------------------
# El enlace
# ---------------------------------------------------------------------------


def test_el_token_solo_viaja_al_crear_el_enlace(client):
    token = _token_contador(client, "portal-01@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)

    creado = _enlace(client, token, contribuyente_id, periodo_id)
    assert creado["token"]
    assert creado["ruta"] == f"/carga/{creado['token']}"

    listado = client.get(
        f"/contribuyentes/{contribuyente_id}/enlaces-carga", headers=_h(token)
    ).json()
    assert len(listado) == 1
    # Si el contador pierde el enlace, genera otro: no hay forma de recuperarlo.
    assert "token" not in listado[0]
    assert listado[0]["prefijo"] == creado["token"][:8]
    assert listado[0]["vigente"] is True


def test_un_token_inventado_no_abre_nada(client):
    assert client.get("/carga/estonoesuntoken").status_code == 404


def test_el_enlace_revocado_responde_410(client):
    token = _token_contador(client, "portal-02@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)
    enlace = _enlace(client, token, contribuyente_id, periodo_id)

    assert client.get(f"/carga/{enlace['token']}").status_code == 200
    revocado = client.post(
        f"/contribuyentes/{contribuyente_id}/enlaces-carga/{enlace['id']}/revocar",
        headers=_h(token),
    )
    assert revocado.status_code == 200
    assert revocado.json()["vigente"] is False
    assert client.get(f"/carga/{enlace['token']}").status_code == 410


def test_generar_un_enlace_nuevo_revoca_el_anterior(client):
    token = _token_contador(client, "portal-03@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)
    primero = _enlace(client, token, contribuyente_id, periodo_id)
    segundo = _enlace(client, token, contribuyente_id, periodo_id)

    assert client.get(f"/carga/{primero['token']}").status_code == 410
    assert client.get(f"/carga/{segundo['token']}").status_code == 200


def test_el_enlace_vencido_responde_410(client, session):
    token = _token_contador(client, "portal-04@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)
    enlace = _enlace(client, token, contribuyente_id, periodo_id)

    fila = session.exec(select(EnlaceCarga).where(EnlaceCarga.id == enlace["id"])).one()
    fila.expira_en = datetime.now(timezone.utc) - timedelta(days=1)
    session.add(fila)
    session.commit()

    assert client.get(f"/carga/{enlace['token']}").status_code == 410


def test_el_enlace_es_reanudable(client):
    """Abrirlo no lo consume: el contribuyente puede volver y seguir."""
    _, _, _, enlace = _preparar(client, "portal-05@example.com")
    primera = client.get(f"/carga/{enlace['token']}")
    segunda = client.get(f"/carga/{enlace['token']}")

    assert primera.status_code == segunda.status_code == 200
    assert primera.json()["requerimientos"] == segunda.json()["requerimientos"]


def test_un_contador_no_genera_enlaces_de_contribuyentes_de_otro(client):
    token_a = _token_contador(client, "portal-06a@example.com")
    token_b = _token_contador(client, "portal-06b@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token_a)

    respuesta = client.post(
        f"/contribuyentes/{contribuyente_id}/enlaces-carga",
        json={"periodo_fiscal_id": periodo_id},
        headers=_h(token_b),
    )
    assert respuesta.status_code == 404


def test_el_portal_enmascara_el_documento(client):
    _, _, _, enlace = _preparar(client, "portal-07@example.com", cargar=False)
    cuerpo = client.get(f"/carga/{enlace['token']}").json()

    assert cuerpo["contribuyente_nombre"] == "Contribuyente Ejemplo"
    assert cuerpo["documento_enmascarado"].endswith(CONSULTANTE[-4:])
    assert CONSULTANTE not in cuerpo["documento_enmascarado"]


def test_el_portal_no_expone_la_liquidacion(client):
    """El alcance del enlace no alcanza a nada del motor de liquidación."""
    _, contribuyente_id, periodo_id, enlace = _preparar(client, "portal-08@example.com")
    cuerpo = client.get(f"/carga/{enlace['token']}").json()

    prohibidos = {"liquidacion", "renglones", "saldo_a_pagar", "impuesto", "hoja"}
    assert prohibidos.isdisjoint(cuerpo.keys())

    # Y el token del portal no sirve como sesión de contador: 401, no 200.
    # `/cartera` y la conciliación existen y responden exactamente 401, que es
    # lo que prueba que el token no se acepta como credencial.
    for ruta in (
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/conciliacion",
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/borrador-renglones",
        "/cartera",
    ):
        assert client.get(
            ruta, headers={"Authorization": f"Bearer {enlace['token']}"}
        ).status_code == 401


# ---------------------------------------------------------------------------
# Política de tratamiento de datos
# ---------------------------------------------------------------------------


def test_sin_aceptar_la_politica_no_se_puede_cargar_nada(client):
    token = _token_contador(client, "portal-09@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)
    enlace = _enlace(client, token, contribuyente_id, periodo_id)

    assert client.get(f"/carga/{enlace['token']}").json()["autorizacion"] is None
    assert _cargar(client, enlace["token"]).status_code == 409


def test_la_aceptacion_queda_con_su_version_y_su_fecha(client):
    token = _token_contador(client, "portal-10@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)
    enlace = _enlace(client, token, contribuyente_id, periodo_id)

    respuesta = _aceptar(client, enlace["token"])
    assert respuesta.status_code == 201
    autorizacion = respuesta.json()
    assert autorizacion["version_politica"]
    assert autorizacion["aceptada_en"]
    assert autorizacion["nombre_quien_acepta"] == "Contribuyente Ejemplo"

    # Y el contador lo ve desde su lado, sin entrar al portal.
    enlaces = client.get(
        f"/contribuyentes/{contribuyente_id}/enlaces-carga", headers=_h(token)
    ).json()
    assert enlaces[0]["politica_aceptada"] is True
    assert enlaces[0]["version_politica_aceptada"] == autorizacion["version_politica"]


def test_la_autorizacion_tiene_que_ser_expresa(client):
    token = _token_contador(client, "portal-11@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)
    enlace = _enlace(client, token, contribuyente_id, periodo_id)
    version = client.get(f"/carga/{enlace['token']}").json()["politica"]["version"]

    respuesta = client.post(
        f"/carga/{enlace['token']}/politica",
        json={
            "version_politica": version,
            "nombre_quien_acepta": "Contribuyente Ejemplo",
            "acepto": False,
        },
    )
    assert respuesta.status_code == 409


def test_no_se_acepta_una_version_de_politica_que_no_existe(client):
    token = _token_contador(client, "portal-12@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)
    enlace = _enlace(client, token, contribuyente_id, periodo_id)

    respuesta = client.post(
        f"/carga/{enlace['token']}/politica",
        json={
            "version_politica": "1999.9",
            "nombre_quien_acepta": "Contribuyente Ejemplo",
            "acepto": True,
        },
    )
    assert respuesta.status_code == 409


# ---------------------------------------------------------------------------
# Carga y versionado de la exógena
# ---------------------------------------------------------------------------


def test_la_carga_guarda_la_fecha_de_corte_y_la_version(client):
    token = _token_contador(client, "portal-13@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)
    enlace = _enlace(client, token, contribuyente_id, periodo_id)
    _aceptar(client, enlace["token"])

    primera = _cargar(client, enlace["token"], _libro(f"{ANIO + 1}-03-14 00:00:00")).json()
    assert primera["version"] == 1
    assert primera["fecha_corte"] == f"{ANIO + 1}-03-14"
    assert primera["cantidad_registros"] == len(FILAS)

    segunda = _cargar(client, enlace["token"], _libro(f"{ANIO + 1}-09-13 00:00:00")).json()
    assert segunda["version"] == 2
    assert segunda["fecha_corte"] == f"{ANIO + 1}-09-13"


def test_el_archivo_de_otro_anio_gravable_se_avisa(client):
    token = _token_contador(client, "portal-14@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)

    respuesta = client.post(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/exogena",
        files={"archivo": ("exogena.xlsx", _libro(anio=ANIO - 1), XLSX)},
        headers=_h(token),
    )
    assert respuesta.status_code == 201
    advertencias = " ".join(respuesta.json()["advertencias"])
    assert str(ANIO - 1) in advertencias and str(ANIO) in advertencias


# ---------------------------------------------------------------------------
# Requerimientos en lenguaje común
# ---------------------------------------------------------------------------


def test_cada_fila_se_traduce_a_un_requerimiento(client):
    _, _, _, enlace = _preparar(client, "portal-15@example.com")
    requerimientos = client.get(f"/carga/{enlace['token']}").json()["requerimientos"]

    # Ninguna fila se descarta: hay exactamente un requerimiento por fila.
    assert len(requerimientos) == len(FILAS)


def test_el_titulo_usa_el_nombre_del_tercero_y_no_el_concepto(client):
    _, _, _, enlace = _preparar(client, "portal-16@example.com")
    requerimientos = client.get(f"/carga/{enlace['token']}").json()["requerimientos"]
    titulos = [r["titulo"] for r in requerimientos]

    assert any("Bancolombia" in t for t in titulos)
    assert any("Clinica" in t or "Clínica" in t for t in titulos)
    # Y en ningún título aparece el código del concepto tributario.
    assert not any("1110" in t or "5001" in t or "Concepto" in t for t in titulos)


def test_el_concepto_que_no_se_reconoce_no_se_descarta(client):
    _, _, _, enlace = _preparar(client, "portal-17@example.com")
    requerimientos = client.get(f"/carga/{enlace['token']}").json()["requerimientos"]

    raro = next(r for r in requerimientos if "Entidad Rara" in r["titulo"])
    assert raro["concepto_reconocido"] is False
    assert raro["motivo_revision"]
    # El valor y el detalle original se conservan tal como vinieron.
    assert raro["valor_exogena"] == 1_200_000
    assert "Zarandeo" in raro["detalle_original"]


def test_lo_que_la_dian_consolida_no_se_cobra_como_pendiente(client):
    _, _, _, enlace = _preparar(client, "portal-18@example.com")
    cuerpo = client.get(f"/carga/{enlace['token']}").json()

    informativa = next(
        r for r in cuerpo["requerimientos"] if "patrimonio bruto" in (r["detalle_original"] or "")
    )
    assert informativa["requiere_soporte"] is False
    assert informativa["resuelto"] is True
    # Tres filas piden soporte; la autorreportada no.
    assert cuerpo["resumen"]["total"] == len(FILAS) - 1


def test_el_estado_es_obligatorio_y_el_valor_opcional(client):
    _, _, _, enlace = _preparar(client, "portal-19@example.com")
    requerimiento = client.get(f"/carga/{enlace['token']}").json()["requerimientos"][0]
    url = f"/carga/{enlace['token']}/requerimientos/{requerimiento['id']}"

    # Sin estado no pasa.
    assert client.patch(url, json={"valor_informado": 100}).status_code == 422
    # Con estado y sin valor, sí.
    respuesta = client.patch(url, json={"estado": "NO_APLICA"})
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "NO_APLICA"
    assert respuesta.json()["valor_informado"] is None


@pytest.mark.parametrize("estado", ["PENDIENTE", "NO_APLICA", "NO_LO_TENGO", "NO_ENTIENDO"])
def test_los_cuatro_estados_se_pueden_marcar(client, estado):
    _, _, _, enlace = _preparar(client, f"portal-20-{estado.lower()}@example.com")
    requerimiento = client.get(f"/carga/{enlace['token']}").json()["requerimientos"][0]

    respuesta = client.patch(
        f"/carga/{enlace['token']}/requerimientos/{requerimiento['id']}",
        json={"estado": estado, "nota_contribuyente": "una nota"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == estado


def test_no_entiendo_no_resuelve_el_requerimiento(client):
    """Es el contribuyente pidiendo ayuda, no el ítem cerrándose."""
    _, _, _, enlace = _preparar(client, "portal-21@example.com")
    requerimiento = next(
        r
        for r in client.get(f"/carga/{enlace['token']}").json()["requerimientos"]
        if r["requiere_soporte"]
    )

    respuesta = client.patch(
        f"/carga/{enlace['token']}/requerimientos/{requerimiento['id']}",
        json={"estado": "NO_ENTIENDO"},
    )
    assert respuesta.json()["resuelto"] is False
    assert client.get(f"/carga/{enlace['token']}").json()["resumen"]["no_entiendo"] == 1


def test_el_soporte_queda_atado_a_su_requerimiento(client):
    token, contribuyente_id, periodo_id, enlace = _preparar(client, "portal-22@example.com")
    requerimiento = next(
        r
        for r in client.get(f"/carga/{enlace['token']}").json()["requerimientos"]
        if r["requiere_soporte"]
    )

    respuesta = client.post(
        f"/carga/{enlace['token']}/requerimientos/{requerimiento['id']}/archivos",
        files={"archivo": ("extracto.pdf", b"%PDF-1.4 soporte de prueba", "application/pdf")},
    )
    assert respuesta.status_code == 201, respuesta.text
    adjunto = respuesta.json()
    assert adjunto["entidad_tipo"] == "REQUERIMIENTO"
    assert adjunto["entidad_id"] == requerimiento["id"]
    assert adjunto["periodo_fiscal_id"] == periodo_id

    vuelto = client.get(f"/carga/{enlace['token']}").json()
    cargado = next(r for r in vuelto["requerimientos"] if r["id"] == requerimiento["id"])
    assert len(cargado["archivos"]) == 1
    assert cargado["resuelto"] is True

    # Y el contador lo ve desde su propia lista de soportes.
    adjuntos = client.get(
        f"/contribuyentes/{contribuyente_id}/adjuntos?entidad_tipo=REQUERIMIENTO",
        headers=_h(token),
    ).json()
    assert len(adjuntos) == 1
    assert adjuntos[0]["etiqueta_entidad"] == requerimiento["titulo"]


def test_recargar_la_exogena_no_borra_el_trabajo_del_contribuyente(client):
    _, _, _, enlace = _preparar(client, "portal-23@example.com")
    antes = client.get(f"/carga/{enlace['token']}").json()["requerimientos"]
    objetivo = next(r for r in antes if "Bancolombia" in r["titulo"])

    client.patch(
        f"/carga/{enlace['token']}/requerimientos/{objetivo['id']}",
        json={"estado": "NO_LO_TENGO", "nota_contribuyente": "cerré esa cuenta"},
    )
    client.post(
        f"/carga/{enlace['token']}/requerimientos/{objetivo['id']}/archivos",
        files={"archivo": ("extracto.pdf", b"%PDF-1.4 soporte", "application/pdf")},
    )

    segunda = _cargar(client, enlace["token"], _libro(f"{ANIO + 1}-09-13 00:00:00")).json()
    assert segunda["requerimientos_creados"] == 0
    assert segunda["requerimientos_actualizados"] == len(FILAS)

    despues = client.get(f"/carga/{enlace['token']}").json()["requerimientos"]
    assert len(despues) == len(FILAS)
    mismo = next(r for r in despues if r["id"] == objetivo["id"])
    assert mismo["estado"] == "NO_LO_TENGO"
    assert mismo["nota_contribuyente"] == "cerré esa cuenta"
    assert len(mismo["archivos"]) == 1


def test_el_contador_puede_dar_por_revisado_un_concepto_sin_clasificar(client):
    token, contribuyente_id, periodo_id, enlace = _preparar(client, "portal-24@example.com")
    raro = next(
        r
        for r in client.get(
            f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/requerimientos",
            headers=_h(token),
        ).json()
        if not r["concepto_reconocido"]
    )

    respuesta = client.patch(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}"
        f"/requerimientos/{raro['id']}/revision",
        headers=_h(token),
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["revisado_por_contador"] is True

    resumen = client.get(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}"
        "/requerimientos/resumen",
        headers=_h(token),
    ).json()
    assert resumen["sin_reconocer"] == 0


def test_el_contador_que_carga_el_archivo_tambien_genera_requerimientos(client):
    """Da igual quién suba el archivo: el camino es uno solo."""
    token = _token_contador(client, "portal-25@example.com")
    contribuyente_id, periodo_id = _contribuyente(client, token)

    client.post(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/exogena",
        files={"archivo": ("exogena.xlsx", _libro(), XLSX)},
        headers=_h(token),
    )

    requerimientos = client.get(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/requerimientos",
        headers=_h(token),
    ).json()
    assert len(requerimientos) == len(FILAS)


# ---------------------------------------------------------------------------
# Adicionales
# ---------------------------------------------------------------------------


def _agregar(client, portal_token, **datos):
    return client.post(f"/carga/{portal_token}/adicionales", json=datos)


def test_los_topes_del_formulario_salen_de_la_tabla_del_anio(client):
    _, _, _, enlace = _preparar(client, "portal-26@example.com", cargar=False)
    parametros = client.get(f"/carga/{enlace['token']}/adicionales/parametros").json()

    assert parametros["anio_gravable"] == ANIO
    assert float(parametros["uvt"]) == float(UVT)
    conceptos = {c["tipo"]: c for c in parametros["conceptos"]}
    # Los ocho conceptos que la exógena nunca trae.
    assert set(conceptos) == {
        "DEPENDIENTE", "INTERESES_VIVIENDA", "MEDICINA_PREPAGADA", "AHORRO_AFC",
        "APORTES_VOLUNTARIOS_PENSION", "ACTIVO", "DEUDA", "BIEN_EXTERIOR",
    }
    assert float(conceptos["INTERESES_VIVIENDA"]["tope_anual_en_pesos"]) == float(TOPE_VIVIENDA)
    assert conceptos["MEDICINA_PREPAGADA"]["es_tope_mensual"] is True
    assert conceptos["AHORRO_AFC"]["grupo_tope_compartido"] == "AHORRO_PREVISIONAL"
    # Cada tope dice de qué norma sale.
    assert conceptos["INTERESES_VIVIENDA"]["fuente_legal"]
    # Un activo o una deuda valen lo que valen: no tienen tope legal.
    assert conceptos["ACTIVO"]["tope_anual_en_pesos"] is None


def test_un_adicional_dentro_del_tope_se_acepta(client):
    _, _, _, enlace = _preparar(client, "portal-27@example.com", cargar=False)

    respuesta = _agregar(
        client,
        enlace["token"],
        tipo="INTERESES_VIVIENDA",
        descripcion="Crédito Banco Ejemplo",
        valor=TOPE_VIVIENDA - 1,
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["capturado_en_portal"] is True


def test_un_adicional_que_pasa_el_tope_se_rechaza_con_la_norma(client):
    _, _, _, enlace = _preparar(client, "portal-28@example.com", cargar=False)

    respuesta = _agregar(
        client,
        enlace["token"],
        tipo="INTERESES_VIVIENDA",
        descripcion="Crédito Banco Ejemplo",
        valor=TOPE_VIVIENDA + 1,
    )
    assert respuesta.status_code == 422
    assert "Art. 119" in respuesta.json()["detail"]


def test_afc_y_pension_voluntaria_comparten_el_tope(client):
    """3.800 UVT entre los dos, no 3.800 cada uno."""
    _, _, _, enlace = _preparar(client, "portal-29@example.com", cargar=False)

    primera = _agregar(
        client, enlace["token"], tipo="AHORRO_AFC",
        descripcion="Cuenta AFC", valor=TOPE_PREVISIONAL - 1000,
    )
    assert primera.status_code == 201

    segunda = _agregar(
        client, enlace["token"], tipo="APORTES_VOLUNTARIOS_PENSION",
        descripcion="Pensión voluntaria", valor=5000,
    )
    assert segunda.status_code == 422
    assert "compartido" in segunda.json()["detail"]


def test_los_dependientes_se_limitan_al_maximo_del_anio(client):
    _, _, _, enlace = _preparar(client, "portal-30@example.com", cargar=False)

    assert _agregar(
        client, enlace["token"], tipo="DEPENDIENTE",
        descripcion="Hijos menores", cantidad=MAX_DEPENDIENTES,
    ).status_code == 201

    excede = _agregar(
        client, enlace["token"], tipo="DEPENDIENTE", descripcion="Madre", cantidad=1
    )
    assert excede.status_code == 422
    assert str(MAX_DEPENDIENTES) in excede.json()["detail"]


def test_un_bien_del_exterior_pide_el_pais(client):
    _, _, _, enlace = _preparar(client, "portal-31@example.com", cargar=False)

    sin_pais = _agregar(
        client, enlace["token"], tipo="BIEN_EXTERIOR",
        descripcion="Cuenta en el exterior", valor=10_000_000,
    )
    assert sin_pais.status_code == 422

    con_pais = _agregar(
        client, enlace["token"], tipo="BIEN_EXTERIOR",
        descripcion="Cuenta en el exterior", valor=10_000_000, pais="España",
    )
    assert con_pais.status_code == 201


def test_cada_adicional_pide_su_propio_soporte(client):
    _, _, _, enlace = _preparar(client, "portal-32@example.com", cargar=False)
    _agregar(
        client, enlace["token"], tipo="MEDICINA_PREPAGADA",
        descripcion="Póliza Ejemplo", valor=2_000_000,
    )

    cuerpo = client.get(f"/carga/{enlace['token']}").json()
    assert len(cuerpo["adicionales"]) == 1
    requerimiento = next(r for r in cuerpo["requerimientos"] if r["origen"] == "ADICIONAL")
    assert "Póliza Ejemplo" in requerimiento["titulo"]
    assert requerimiento["requiere_soporte"] is True


def test_un_adicional_con_soportes_no_se_borra_en_silencio(client):
    _, _, _, enlace = _preparar(client, "portal-33@example.com", cargar=False)
    adicional = _agregar(
        client, enlace["token"], tipo="MEDICINA_PREPAGADA",
        descripcion="Póliza Ejemplo", valor=2_000_000,
    ).json()
    requerimiento = next(
        r
        for r in client.get(f"/carga/{enlace['token']}").json()["requerimientos"]
        if r["origen"] == "ADICIONAL"
    )
    client.post(
        f"/carga/{enlace['token']}/requerimientos/{requerimiento['id']}/archivos",
        files={"archivo": ("poliza.pdf", b"%PDF-1.4 poliza", "application/pdf")},
    )

    respuesta = client.delete(f"/carga/{enlace['token']}/adicionales/{adicional['id']}")
    assert respuesta.status_code == 422


def test_el_anio_sin_parametros_no_valida_contra_topes_inventados(client):
    """Si la tabla del año no existe, el formulario no se abre a ciegas."""
    token = _token_contador(client, "portal-34@example.com")
    contribuyente_id = client.post(
        "/contribuyentes",
        json={"nombre": "Contribuyente Ejemplo", "rut": CONSULTANTE,
              "tipo_contribuyente": "MIXTO"},
        headers=_h(token),
    ).json()["id"]
    periodo_id = client.post(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales",
        json={"anio_gravable": 2099},
        headers=_h(token),
    ).json()["id"]
    enlace = _enlace(client, token, contribuyente_id, periodo_id)
    _aceptar(client, enlace["token"])

    assert client.get(f"/carga/{enlace['token']}/adicionales/parametros").status_code == 409
    assert _agregar(
        client, enlace["token"], tipo="INTERESES_VIVIENDA",
        descripcion="Crédito", valor=1_000_000,
    ).status_code == 409


# ---------------------------------------------------------------------------
# Bitácora
# ---------------------------------------------------------------------------


def test_lo_que_hace_el_contribuyente_queda_en_la_bitacora_del_contador(client):
    token, contribuyente_id, _, enlace = _preparar(client, "portal-35@example.com")

    eventos = client.get("/auditoria", headers=_h(token)).json()
    acciones = {e["accion"] for e in eventos}
    assert "aceptar_politica" in acciones
    assert "cargar_exogena" in acciones
    # Quedan atados al contribuyente, no sueltos.
    assert all(
        e["contribuyente_id"] == contribuyente_id
        for e in eventos
        if e["accion"] in {"aceptar_politica", "cargar_exogena"}
    )


def test_la_bitacora_no_guarda_el_token_del_enlace(client):
    """Anotar la llave en un registro que se exporta y se respalda no sirve."""
    token, _, _, enlace = _preparar(client, "portal-36@example.com")

    eventos = client.get("/auditoria", headers=_h(token)).json()
    assert eventos
    for evento in eventos:
        assert enlace["token"] not in evento["ruta"]
