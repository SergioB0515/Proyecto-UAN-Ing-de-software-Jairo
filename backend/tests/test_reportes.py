"""Pruebas del módulo de reportes: cierre y reapertura de periodo (HU-15),
reportes exportables (HU-16) y resumen por contribuyente (HU-17)."""
import io
from pathlib import Path

import openpyxl
import pytest

RUTA_FIXTURE = Path(__file__).parent / "fixtures" / "reporte_exogena_ejemplo.xlsx"


def _crear_contador_y_token(client, email: str) -> str:
    client.post(
        "/contadores/registro",
        json={"nombre": "Contador de prueba", "email": email, "contrasena": "claveDePrueba1"},
    )
    login = client.post(
        "/contadores/login", data={"username": email, "password": "claveDePrueba1"}
    )
    return login.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class Escenario:
    """Contador + contribuyente + periodos, con atajos para inventario."""

    def __init__(self, client, email: str, tipo: str = "INDEPENDIENTE", anios=(2025,)):
        self.client = client
        self.h = _headers(_crear_contador_y_token(client, email))
        self.cid = client.post(
            "/contribuyentes",
            json={"nombre": "Contribuyente Ejemplo", "rut": "1000000000", "tipo_contribuyente": tipo},
            headers=self.h,
        ).json()["id"]
        self.periodos = {
            anio: client.post(
                f"/contribuyentes/{self.cid}/periodos-fiscales",
                json={"anio_gravable": anio},
                headers=self.h,
            ).json()["id"]
            for anio in anios
        }
        if tipo != "ASALARIADO":
            self.documento_id = client.post(
                f"/contribuyentes/{self.cid}/documentos-soporte",
                json={"tipo": "FACTURA", "numero": "FV-1", "fecha": "2025-01-01"},
                headers=self.h,
            ).json()["id"]
            self.producto_id = client.post(
                f"/contribuyentes/{self.cid}/productos",
                json={"codigo": "P-1", "nombre": "Arroz", "clasificacion_iva": "EXCLUIDO", "metodo_costeo": "PEPS"},
                headers=self.h,
            ).json()["id"]

    def url(self, anio: int, sufijo: str) -> str:
        return f"/contribuyentes/{self.cid}/periodos-fiscales/{self.periodos[anio]}/{sufijo}"

    def movimiento(self, tipo, cantidad, valor_unitario, fecha):
        anio = int(fecha[:4])
        return self.client.post(
            f"/contribuyentes/{self.cid}/movimientos",
            json={
                "tipo": tipo,
                "producto_id": self.producto_id,
                "periodo_fiscal_id": self.periodos[anio],
                "documento_soporte_id": self.documento_id,
                "fecha": fecha,
                "cantidad": cantidad,
                "valor_unitario": valor_unitario,
            },
            headers=self.h,
        )

    def importar_exogena(self, anio: int = 2025):
        with open(RUTA_FIXTURE, "rb") as archivo:
            return self.client.post(
                self.url(anio, "exogena"),
                files={"archivo": ("exogena.xlsx", archivo, "application/octet-stream")},
                headers=self.h,
            )

    def patrimonio(self) -> float:
        return self.client.get(
            f"/contribuyentes/{self.cid}/patrimonio", headers=self.h
        ).json()["patrimonio_liquido"]


# ------------------------------------------------------------------ Cierre


def test_cerrar_periodo_lleva_el_inventario_al_patrimonio(client):
    e = Escenario(client, "rep-1@example.com")
    e.movimiento("ENTRADA", 10, 100, "2025-03-01")

    respuesta = client.post(e.url(2025, "cerrar"), headers=e.h)

    assert respuesta.status_code == 200
    cierre = respuesta.json()
    assert cierre["estado"] == "CERRADO"
    assert cierre["valor_inventario"] == 1000
    assert cierre["activo_inventario_id"] is not None
    assert e.patrimonio() == 1000

    activos = client.get(f"/contribuyentes/{e.cid}/activos", headers=e.h).json()
    assert activos[0]["tipo"] == "INVENTARIO"


def test_periodo_cerrado_no_admite_movimientos_ni_exogena(client):
    e = Escenario(client, "rep-2@example.com")
    client.post(e.url(2025, "cerrar"), headers=e.h)

    assert e.movimiento("ENTRADA", 1, 100, "2025-05-01").status_code == 409
    assert e.importar_exogena().status_code == 409


def test_cerrar_un_periodo_ya_cerrado_falla(client):
    e = Escenario(client, "rep-3@example.com")
    assert client.post(e.url(2025, "cerrar"), headers=e.h).status_code == 200
    assert client.post(e.url(2025, "cerrar"), headers=e.h).status_code == 409


def test_no_se_cierra_un_anio_con_anteriores_abiertos(client):
    e = Escenario(client, "rep-4@example.com", anios=(2025, 2026))
    respuesta = client.post(e.url(2026, "cerrar"), headers=e.h)
    assert respuesta.status_code == 409
    assert "2025" in respuesta.json()["detail"]


def test_reabrir_deshace_el_cierre(client):
    e = Escenario(client, "rep-5@example.com")
    e.movimiento("ENTRADA", 10, 100, "2025-03-01")
    client.post(e.url(2025, "cerrar"), headers=e.h)

    respuesta = client.post(e.url(2025, "reabrir"), headers=e.h)

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ABIERTO"
    assert e.patrimonio() == 0
    assert client.get(f"/contribuyentes/{e.cid}/activos", headers=e.h).json() == []
    assert e.movimiento("ENTRADA", 1, 100, "2025-05-01").status_code == 201


def test_reabrir_un_periodo_abierto_falla(client):
    e = Escenario(client, "rep-6@example.com")
    assert client.post(e.url(2025, "reabrir"), headers=e.h).status_code == 409


def test_no_se_reabre_un_anio_con_posteriores_cerrados(client):
    e = Escenario(client, "rep-7@example.com", anios=(2025, 2026))
    client.post(e.url(2025, "cerrar"), headers=e.h)
    client.post(e.url(2026, "cerrar"), headers=e.h)

    assert client.post(e.url(2025, "reabrir"), headers=e.h).status_code == 409
    assert client.post(e.url(2026, "reabrir"), headers=e.h).status_code == 200


def test_el_patrimonio_cuenta_solo_el_inventario_del_ultimo_cierre(client):
    e = Escenario(client, "rep-8@example.com", anios=(2025, 2026))
    e.movimiento("ENTRADA", 10, 100, "2025-03-01")
    client.post(e.url(2025, "cerrar"), headers=e.h)
    e.movimiento("SALIDA", 4, 150, "2026-02-01")

    cierre_2026 = client.post(e.url(2026, "cerrar"), headers=e.h).json()

    assert cierre_2026["valor_inventario"] == 600
    assert cierre_2026["costo_ventas"] == 400
    # 600 del inventario de 2026, no 1.000 + 600.
    assert e.patrimonio() == 600


def test_cerrar_periodo_de_asalariado_no_crea_inventario(client):
    e = Escenario(client, "rep-9@example.com", tipo="ASALARIADO")
    cierre = client.post(e.url(2025, "cerrar"), headers=e.h).json()
    assert cierre["estado"] == "CERRADO"
    assert cierre["activo_inventario_id"] is None


def test_no_se_registra_un_activo_inventario_a_mano(client):
    e = Escenario(client, "rep-10@example.com")
    respuesta = client.post(
        f"/contribuyentes/{e.cid}/activos",
        json={"descripcion": "Inventario", "tipo": "INVENTARIO", "valor": 1000,
              "periodo_fiscal_id": e.periodos[2025]},
        headers=e.h,
    )
    assert respuesta.status_code == 422


def test_un_contador_no_cierra_periodos_de_otro(client):
    e = Escenario(client, "rep-11a@example.com")
    otro = _headers(_crear_contador_y_token(client, "rep-11b@example.com"))
    assert client.post(e.url(2025, "cerrar"), headers=otro).status_code == 404


# ----------------------------------------------------------------- Resumen


def test_resumen_de_asalariado_sin_exogena(client):
    e = Escenario(client, "rep-12@example.com", tipo="ASALARIADO")
    client.post(
        f"/contribuyentes/{e.cid}/fuentes-ingreso",
        json={"concepto": "Salario", "valor_anual": 60000000, "retencion_fuente": 2000000,
              "periodo_fiscal_id": e.periodos[2025]},
        headers=e.h,
    )

    respuesta = client.get(e.url(2025, "resumen"), headers=e.h)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["anio_gravable"] == 2025
    assert cuerpo["inventario"] is None  # HU-17: un asalariado no tiene inventario
    assert cuerpo["ingresos"]["total_ingresos"] == 60000000
    assert cuerpo["ingresos"]["total_retenciones"] == 2000000
    assert cuerpo["obligacion"] is None
    assert any("exógena" in aviso for aviso in cuerpo["avisos"])


def test_resumen_completo_con_exogena_y_umbral(client):
    e = Escenario(client, "rep-13@example.com")
    e.importar_exogena()
    client.post(
        "/parametros/umbrales",
        json={
            "anio_gravable": 2025, "valor_uvt": 49799, "tope_ingresos_uvt": 1400,
            "tope_patrimonio_uvt": 4500, "tope_consumo_tc_uvt": 1400,
            "tope_compras_uvt": 1400, "tope_movimiento_uvt": 1400,
        },
        headers=e.h,
    )
    e.movimiento("ENTRADA", 10, 100, "2025-03-01")

    cuerpo = client.get(e.url(2025, "resumen"), headers=e.h).json()

    assert cuerpo["inventario"]["inventario_final"] == 1000
    assert cuerpo["obligacion"]["obligado"] is False
    assert cuerpo["conciliacion"]["NO_DECLARADO"] == 5


# -------------------------------------------------------- Reportes exportables


@pytest.mark.parametrize(
    "tipo", ["kardex", "saldo-inventario", "conciliacion", "borrador-renglones", "resumen"]
)
def test_cada_reporte_se_exporta_en_excel_y_pdf(client, tipo):
    e = Escenario(client, f"rep-14-{tipo}@example.com")
    e.importar_exogena()
    e.movimiento("ENTRADA", 10, 100, "2025-03-01")
    e.movimiento("SALIDA", 3, 180, "2025-04-01")

    excel = client.get(e.url(2025, f"reportes/{tipo}?formato=xlsx"), headers=e.h)
    assert excel.status_code == 200
    assert excel.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert f"{tipo}_1000000000_2025.xlsx" in excel.headers["content-disposition"]
    hoja = openpyxl.load_workbook(io.BytesIO(excel.content)).active
    assert "Contribuyente Ejemplo" in hoja["A2"].value

    pdf = client.get(e.url(2025, f"reportes/{tipo}?formato=pdf"), headers=e.h)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_reporte_de_kardex_trae_los_valores_del_costeo(client):
    e = Escenario(client, "rep-15@example.com")
    e.movimiento("ENTRADA", 10, 100, "2025-03-01")
    e.movimiento("SALIDA", 3, 180, "2025-04-01")

    excel = client.get(e.url(2025, "reportes/kardex"), headers=e.h)
    valores = [
        celda for fila in openpyxl.load_workbook(io.BytesIO(excel.content)).active.values
        for celda in fila
    ]
    assert "Saldo inicial" in valores and "Saldo final" in valores
    assert 300 in valores  # costo de la salida: 3 x 100
    assert 700 in valores  # saldo final valorizado


def test_reporte_de_inventario_para_asalariado_falla(client):
    e = Escenario(client, "rep-16@example.com", tipo="ASALARIADO")
    assert client.get(e.url(2025, "reportes/kardex"), headers=e.h).status_code == 409


def test_reporte_de_conciliacion_sin_exogena_falla(client):
    e = Escenario(client, "rep-17@example.com")
    assert client.get(e.url(2025, "reportes/conciliacion"), headers=e.h).status_code == 404


def test_reporte_o_formato_inexistente_falla(client):
    e = Escenario(client, "rep-18@example.com")
    assert client.get(e.url(2025, "reportes/balance"), headers=e.h).status_code == 422
    assert client.get(e.url(2025, "reportes/resumen?formato=docx"), headers=e.h).status_code == 422
