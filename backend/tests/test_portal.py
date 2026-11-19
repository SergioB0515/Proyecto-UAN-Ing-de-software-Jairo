"""Pruebas del portal de carga del contribuyente.

Lo que se verifica aquí:

* el alcance del enlace (un contribuyente, un periodo, revocable, reanudable);
* que el token no se pueda recuperar después de generarlo;
* que sin aceptar la política no se escriba nada;
* que la lista de documentos del portal sea LA MISMA que ve el contador, no
  una paralela;
* que los conceptos que la aplicación no reconoce queden marcados;
* que los topes del formulario de adicionales salgan de la tabla del año;
* que ninguna respuesta del portal arrastre la liquidación.
"""

import io
from datetime import datetime, timedelta, timezone

import openpyxl
import pytest
from sqlmodel import select

from modulos.parametros.tablas_oficiales import PARAMETROS_POR_ANIO
from modulos.portal.modelos import EnlaceCarga

ANIO = 2025

# Los topes se calculan desde la tabla del año y NO se escriben a mano: si la
# tabla cambia, la prueba sigue valiendo.
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


def _documentos(client, portal_token: str):
    return client.get(f"/carga/{portal_token}/documentos").json()


def _doc(documentos, contiene: str):
    return next(
        d for d in documentos
        if contiene.lower() in f"{d['descripcion']} {d['tercero']}".lower()
    )


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
    assert primera.json()["documentos"] == segunda.json()["documentos"]


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


# ---------------------------------------------------------------------------
# El alcance: nada de liquidación sale por el enlace
# ---------------------------------------------------------------------------

# Campos que solo existen en la liquidación, el borrador o la cartera. Si
# alguno aparece en el esquema de una respuesta del portal, algo se filtró.
_PROHIBIDOS = {
    "saldo_a_pagar", "saldo_a_favor", "impuesto_neto", "total_a_cargo",
    "renta_liquida", "renglones", "casillas", "anticipo", "retenciones",
    "base_gravable", "ganancia_ocasional", "alertas_no_declarado", "obligado",
    "mensaje",
}


def _campos_del_esquema(spec, referencia, vistos=None) -> set:
    """Todos los nombres de campo alcanzables desde un esquema, recursivo."""
    vistos = vistos if vistos is not None else set()
    nombre = referencia.split("/")[-1]
    if nombre in vistos:
        return set()
    vistos.add(nombre)
    esquema = spec["components"]["schemas"].get(nombre, {})
    campos = set(esquema.get("properties", {}))
    for propiedad in esquema.get("properties", {}).values():
        for rama in [propiedad] + propiedad.get("anyOf", []) + propiedad.get("allOf", []):
            if "$ref" in rama:
                campos |= _campos_del_esquema(spec, rama["$ref"], vistos)
            items = rama.get("items", {})
            if "$ref" in items:
                campos |= _campos_del_esquema(spec, items["$ref"], vistos)
    return campos


def test_ninguna_respuesta_del_portal_arrastra_la_liquidacion(client):
    """La garantía del enlace, verificada sobre el esquema de las respuestas.

    Antes esto se sostenía por los imports del módulo. Ahora la lista de
    documentos viene de `gestion`, que sí lee la liquidación para saber qué
    pedir, así que la garantía se verifica donde importa: en lo que el portal
    puede devolver. Esta prueba falla si alguien expone un campo de más.
    """
    spec = client.get("/openapi.json").json()
    rutas = [p for p in spec["paths"] if p.startswith("/carga/")]
    assert rutas, "el portal público no está montado"

    for ruta in rutas:
        for metodo, operacion in spec["paths"][ruta].items():
            contenido = (
                operacion.get("responses", {}).get("200", {}).get("content", {})
                or operacion.get("responses", {}).get("201", {}).get("content", {})
            )
            esquema = contenido.get("application/json", {}).get("schema", {})
            referencia = esquema.get("$ref") or esquema.get("items", {}).get("$ref")
            if not referencia:
                continue
            filtrados = _campos_del_esquema(spec, referencia) & _PROHIBIDOS
            assert not filtrados, (
                f"{metodo.upper()} {ruta} expone {sorted(filtrados)}"
            )


def test_el_token_del_portal_no_sirve_como_sesion_de_contador(client):
    _, contribuyente_id, periodo_id, enlace = _preparar(client, "portal-08@example.com")

    for ruta in (
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/conciliacion",
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/documentos",
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
    assert primera["documentos_pedidos"] > 0

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
# Documentos: una sola lista
# ---------------------------------------------------------------------------


def test_el_portal_y_el_contador_ven_la_misma_lista(client):
    """No hay dos bandejas de «lo que falta»: es la misma tabla."""
    token, contribuyente_id, periodo_id, enlace = _preparar(client, "portal-15@example.com")

    del_portal = _documentos(client, enlace["token"])
    del_contador = client.get(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/documentos",
        headers=_h(token),
    ).json()

    assert {d["clave"] for d in del_portal} == {d["clave"] for d in del_contador["documentos"]}


def test_se_pide_un_documento_por_tercero_y_tipo(client):
    """El nombre del tercero, no el concepto tributario."""
    _, _, _, enlace = _preparar(client, "portal-16@example.com")
    documentos = _documentos(client, enlace["token"])

    assert _doc(documentos, "BANCOLOMBIA")
    assert _doc(documentos, "CLINICA DEL COUNTRY")
    # El concepto tributario no se le muestra al contribuyente.
    for d in documentos:
        assert "1110" not in d["descripcion"] and "5001" not in d["descripcion"]
    # Lo que reporta el propio contribuyente no se le pide a nadie.
    assert not any("CONTRIBUYENTE EJEMPLO" in d["tercero"] for d in documentos)


def test_el_concepto_que_no_se_reconoce_queda_marcado(client):
    _, _, _, enlace = _preparar(client, "portal-17@example.com")
    documentos = _documentos(client, enlace["token"])

    raro = _doc(documentos, "ENTIDAD RARA")
    assert raro["reconocido"] is False
    # No se descarta: el valor que lo originó sigue a la vista del contador.
    assert "Zarandeo" in raro["motivo"]


@pytest.mark.parametrize("estado", ["NO_APLICA", "NO_LO_TENGO", "NO_ENTIENDO"])
def test_el_contribuyente_marca_los_estados_nuevos(client, estado):
    _, _, _, enlace = _preparar(client, f"portal-18-{estado.lower()}@example.com")
    clave = _doc(_documentos(client, enlace["token"]), "BANCOLOMBIA")["clave"]

    respuesta = client.patch(
        f"/carga/{enlace['token']}/documentos/{clave}",
        json={"estado": estado, "nota": "una nota"},
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == estado
    assert cuerpo["respondido_por_contribuyente"] is True


def test_el_estado_es_obligatorio_y_el_valor_opcional(client):
    _, _, _, enlace = _preparar(client, "portal-19@example.com")
    clave = _doc(_documentos(client, enlace["token"]), "BANCOLOMBIA")["clave"]
    url = f"/carga/{enlace['token']}/documentos/{clave}"

    # Con estado y sin valor, pasa.
    sin_valor = client.patch(url, json={"estado": "NO_APLICA"})
    assert sin_valor.status_code == 200
    assert sin_valor.json()["valor_informado"] is None

    # Y el valor se puede informar aparte, sin volver a tocar el estado.
    con_valor = client.patch(url, json={"valor_informado": 14850000})
    assert con_valor.status_code == 200
    assert float(con_valor.json()["valor_informado"]) == 14_850_000
    assert con_valor.json()["estado"] == "NO_APLICA"


def test_no_entiendo_no_resuelve_el_documento(client):
    """Es el contribuyente pidiendo ayuda, no el ítem cerrándose."""
    token, contribuyente_id, periodo_id, enlace = _preparar(client, "portal-20@example.com")
    clave = _doc(_documentos(client, enlace["token"]), "BANCOLOMBIA")["clave"]

    respuesta = client.patch(
        f"/carga/{enlace['token']}/documentos/{clave}", json={"estado": "NO_ENTIENDO"}
    )
    assert respuesta.json()["resuelto"] is False

    solicitud = client.get(
        f"/contribuyentes/{contribuyente_id}/periodos-fiscales/{periodo_id}/documentos",
        headers=_h(token),
    ).json()
    assert solicitud["no_entiendo"] == 1


def test_subir_el_soporte_deja_el_documento_recibido(client):
    """Subir el papel ES recibirlo: no hay que marcar nada después."""
    token, contribuyente_id, periodo_id, enlace = _preparar(client, "portal-21@example.com")
    clave = _doc(_documentos(client, enlace["token"]), "BANCOLOMBIA")["clave"]

    respuesta = client.post(
        f"/carga/{enlace['token']}/documentos/{clave}/archivos",
        files={"archivo": ("extracto.pdf", b"%PDF-1.4 soporte de prueba", "application/pdf")},
    )
    assert respuesta.status_code == 201, respuesta.text
    adjunto = respuesta.json()
    assert adjunto["entidad_tipo"] == "DOCUMENTO_SOLICITADO"
    assert adjunto["periodo_fiscal_id"] == periodo_id

    documento = _doc(_documentos(client, enlace["token"]), "BANCOLOMBIA")
    assert documento["estado"] == "RECIBIDO"
    assert documento["resuelto"] is True
    assert len(documento["archivos"]) == 1
    assert documento["respondido_por_contribuyente"] is True

    # Y el contador lo ve entre sus soportes, atado a ese documento.
    adjuntos = client.get(
        f"/contribuyentes/{contribuyente_id}/adjuntos?entidad_tipo=DOCUMENTO_SOLICITADO",
        headers=_h(token),
    ).json()
    assert len(adjuntos) == 1
    assert adjuntos[0]["etiqueta_entidad"] == documento["descripcion"]


def test_recargar_la_exogena_no_borra_el_trabajo_del_contribuyente(client):
    _, _, _, enlace = _preparar(client, "portal-22@example.com")
    clave = _doc(_documentos(client, enlace["token"]), "BANCOLOMBIA")["clave"]

    client.patch(
        f"/carga/{enlace['token']}/documentos/{clave}",
        json={"estado": "NO_LO_TENGO", "nota": "cerré esa cuenta"},
    )

    assert _cargar(client, enlace["token"], _libro(f"{ANIO + 1}-09-13 00:00:00")).status_code == 201

    documento = _doc(_documentos(client, enlace["token"]), "BANCOLOMBIA")
    assert documento["estado"] == "NO_LO_TENGO"
    assert documento["nota"] == "cerré esa cuenta"


def test_una_clave_que_no_esta_en_la_solicitud_se_rechaza(client):
    _, _, _, enlace = _preparar(client, "portal-23@example.com")

    respuesta = client.patch(
        f"/carga/{enlace['token']}/documentos/NO_EXISTE:1", json={"estado": "NO_APLICA"}
    )
    assert respuesta.status_code == 404


# ---------------------------------------------------------------------------
# Adicionales
# ---------------------------------------------------------------------------


def _agregar(client, portal_token, **datos):
    return client.post(f"/carga/{portal_token}/adicionales", json=datos)


def test_los_topes_del_formulario_salen_de_la_tabla_del_anio(client):
    _, _, _, enlace = _preparar(client, "portal-24@example.com", cargar=False)
    parametros = client.get(f"/carga/{enlace['token']}/adicionales/parametros").json()

    assert parametros["anio_gravable"] == ANIO
    assert float(parametros["uvt"]) == float(UVT)
    conceptos = {c["tipo"]: c for c in parametros["conceptos"]}
    assert set(conceptos) == {
        "DEPENDIENTE", "INTERESES_VIVIENDA", "MEDICINA_PREPAGADA", "AHORRO_AFC",
        "APORTES_VOLUNTARIOS_PENSION", "ACTIVO", "DEUDA", "BIEN_EXTERIOR",
    }
    assert float(conceptos["INTERESES_VIVIENDA"]["tope_anual_en_pesos"]) == float(TOPE_VIVIENDA)
    assert conceptos["MEDICINA_PREPAGADA"]["es_tope_mensual"] is True
    assert conceptos["AHORRO_AFC"]["grupo_tope_compartido"] == "AHORRO_PREVISIONAL"
    assert conceptos["INTERESES_VIVIENDA"]["fuente_legal"]
    # Un activo o una deuda valen lo que valen: no tienen tope legal.
    assert conceptos["ACTIVO"]["tope_anual_en_pesos"] is None


def test_un_adicional_dentro_del_tope_se_acepta(client):
    _, _, _, enlace = _preparar(client, "portal-25@example.com", cargar=False)

    respuesta = _agregar(
        client, enlace["token"], tipo="INTERESES_VIVIENDA",
        descripcion="Crédito Banco Ejemplo", valor=TOPE_VIVIENDA - 1,
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["capturado_en_portal"] is True


def test_un_adicional_que_pasa_el_tope_se_rechaza_con_la_norma(client):
    _, _, _, enlace = _preparar(client, "portal-26@example.com", cargar=False)

    respuesta = _agregar(
        client, enlace["token"], tipo="INTERESES_VIVIENDA",
        descripcion="Crédito Banco Ejemplo", valor=TOPE_VIVIENDA + 1,
    )
    assert respuesta.status_code == 422
    assert "Art. 119" in respuesta.json()["detail"]


def test_afc_y_pension_voluntaria_comparten_el_tope(client):
    """3.800 UVT entre los dos, no 3.800 cada uno."""
    _, _, _, enlace = _preparar(client, "portal-27@example.com", cargar=False)

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
    _, _, _, enlace = _preparar(client, "portal-28@example.com", cargar=False)

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
    _, _, _, enlace = _preparar(client, "portal-29@example.com", cargar=False)

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


def test_un_adicional_agrega_su_documento_a_la_misma_lista(client):
    """No crea una lista aparte: entra a la solicitud que ya existe."""
    _, _, _, enlace = _preparar(client, "portal-30@example.com", cargar=False)
    antes = {d["clave"] for d in _documentos(client, enlace["token"])}

    _agregar(
        client, enlace["token"], tipo="MEDICINA_PREPAGADA",
        descripcion="Póliza Ejemplo", valor=2_000_000,
    )

    despues = _documentos(client, enlace["token"])
    nuevas = {d["clave"] for d in despues} - antes
    assert nuevas == {"DEDUCCION:MEDICINA_PREPAGADA"}
    assert "medicina prepagada" in _doc(despues, "medicina prepagada")["descripcion"].lower()


def test_el_anio_sin_parametros_no_valida_contra_topes_inventados(client):
    """Si la tabla del año no existe, el formulario no se abre a ciegas."""
    token = _token_contador(client, "portal-31@example.com")
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
    token, contribuyente_id, _, enlace = _preparar(client, "portal-32@example.com")

    eventos = client.get("/auditoria", headers=_h(token)).json()
    acciones = {e["accion"] for e in eventos}
    assert "aceptar_politica" in acciones
    assert "cargar_exogena" in acciones
    assert all(
        e["contribuyente_id"] == contribuyente_id
        for e in eventos
        if e["accion"] in {"aceptar_politica", "cargar_exogena"}
    )


def test_la_bitacora_no_guarda_el_token_del_enlace(client):
    """Anotar la llave en un registro que se exporta y se respalda no sirve."""
    token, _, _, enlace = _preparar(client, "portal-33@example.com")

    eventos = client.get("/auditoria", headers=_h(token)).json()
    assert eventos
    for evento in eventos:
        assert enlace["token"] not in evento["ruta"]
