import base64
import csv
import io
import os
import zipfile
from pathlib import Path

import openpyxl

import modulos.adjuntos.servicios as servicios_adjuntos

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 32 + b"\xff\xd9"


def _xlsx() -> bytes:
    libro = openpyxl.Workbook()
    libro.active["A1"] = "transferencia"
    destino = io.BytesIO()
    libro.save(destino)
    return destino.getvalue()


def _registrar(client, email: str) -> dict:
    client.post(
        "/contadores/registro",
        json={"nombre": "Contador", "email": email, "contrasena": "clave-segura-1"},
    )
    token = client.post(
        "/contadores/login", data={"username": email, "password": "clave-segura-1"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class Escenario:
    def __init__(self, client, email: str, tipo: str = "MIXTO"):
        self.client = client
        self.h = _registrar(client, email)
        self.cid = client.post(
            "/contribuyentes",
            json={"nombre": "Ana Pérez", "rut": "1010", "tipo_contribuyente": tipo},
            headers=self.h,
        ).json()["id"]
        self.pid = self.periodo(2025)

    def url(self, sufijo: str = "") -> str:
        return f"/contribuyentes/{self.cid}{sufijo}"

    def periodo(self, anio: int) -> int:
        return self.client.post(
            self.url("/periodos-fiscales"), json={"anio_gravable": anio}, headers=self.h
        ).json()["id"]

    def activo(self, descripcion: str = "Cuenta", **extra) -> int:
        datos = {"descripcion": descripcion, "tipo": "CUENTA", "valor": 1000, "periodo_fiscal_id": self.pid, **extra}
        return self.client.post(self.url("/activos"), json=datos, headers=self.h).json()["id"]

    def fuente(self) -> int:
        datos = {"concepto": "Salario", "valor_anual": 5000, "periodo_fiscal_id": self.pid}
        return self.client.post(self.url("/fuentes-ingreso"), json=datos, headers=self.h).json()["id"]

    def documento(self, numero: str = "FV-1", fecha: str = "2025-03-01") -> int:
        return self.client.post(
            self.url("/documentos-soporte"),
            json={"tipo": "FACTURA", "numero": numero, "fecha": fecha},
            headers=self.h,
        ).json()["id"]

    def proveedor(self) -> int:
        return self.client.post(
            self.url("/proveedores"),
            json={"nombre": "Mayorista", "tipo_persona": "JURIDICA", "identificacion": "900"},
            headers=self.h,
        ).json()["id"]

    def movimiento(self) -> int:
        producto = self.client.post(
            self.url("/productos"),
            json={"codigo": "P1", "nombre": "Arroz", "clasificacion_iva": "GRAVADO", "metodo_costeo": "PEPS"},
            headers=self.h,
        ).json()["id"]
        return self.client.post(
            self.url("/movimientos"),
            json={
                "tipo": "ENTRADA",
                "producto_id": producto,
                "periodo_fiscal_id": self.pid,
                "documento_soporte_id": self.documento("FV-9"),
                "fecha": "2025-02-01",
                "cantidad": 5,
                "valor_unitario": 100,
            },
            headers=self.h,
        ).json()["id"]

    def subir(self, tipo, entidad_id, contenido=PDF, nombre="recibo.pdf", **campos):
        return self.client.post(
            self.url("/adjuntos"),
            data={"entidad_tipo": tipo, "entidad_id": entidad_id, **campos},
            files={"archivo": (nombre, contenido)},
            headers=self.h,
        )

    def listar(self, **params):
        return self.client.get(self.url("/adjuntos"), params=params, headers=self.h).json()


def test_sube_un_pdf_a_un_activo_y_lo_descarga_intacto(client):
    e = Escenario(client, "adj-1@example.com")
    activo = e.activo("Apartamento")
    r = e.subir("ACTIVO", activo, PDF, "Recibo predial.pdf", categoria="RECIBO", descripcion="  Predial 2025  ")
    assert r.status_code == 201
    adjunto = r.json()
    assert adjunto["nombre_original"] == "Recibo predial.pdf"
    assert adjunto["tipo_mime"] == "application/pdf"
    assert adjunto["categoria"] == "RECIBO"
    assert adjunto["descripcion"] == "Predial 2025"
    assert adjunto["etiqueta_entidad"] == "Apartamento"
    assert adjunto["periodo_fiscal_id"] == e.pid
    assert adjunto["previsualizable"] is True
    assert adjunto["tamano_bytes"] == len(PDF)

    archivo = client.get(e.url(f"/adjuntos/{adjunto['id']}/archivo"), headers=e.h)
    assert archivo.status_code == 200
    assert archivo.content == PDF
    assert archivo.headers["content-type"] == "application/pdf"
    assert archivo.headers["content-disposition"].startswith("inline")

    forzado = client.get(e.url(f"/adjuntos/{adjunto['id']}/archivo"), params={"descargar": True}, headers=e.h)
    assert forzado.headers["content-disposition"].startswith("attachment")


def test_la_extension_se_corrige_segun_el_contenido(client):
    e = Escenario(client, "adj-2@example.com")
    activo = e.activo()
    sin_extension = e.subir("ACTIVO", activo, PNG, "captura").json()
    assert sin_extension["nombre_original"] == "captura.png"
    assert sin_extension["tipo_mime"] == "image/png"
    mal_nombrada = e.subir("ACTIVO", activo, JPG, "foto.png").json()
    assert mal_nombrada["nombre_original"] == "foto.jpg"
    assert mal_nombrada["tipo_mime"] == "image/jpeg"


def test_rechaza_archivos_que_no_son_lo_que_dicen(client):
    e = Escenario(client, "adj-3@example.com")
    activo = e.activo()
    assert e.subir("ACTIVO", activo, b"MZ\x90\x00programa", "factura.pdf").status_code == 415
    assert e.subir("ACTIVO", activo, b"<script>alert(1)</script>", "captura.png").status_code == 415
    assert e.subir("ACTIVO", activo, b"<svg onload=alert(1)></svg>", "logo.svg").status_code == 415
    assert e.subir("ACTIVO", activo, b"", "vacio.pdf").status_code == 415

    comprimido = io.BytesIO()
    with zipfile.ZipFile(comprimido, "w") as z:
        z.writestr("programa.exe", "x")
    assert e.subir("ACTIVO", activo, comprimido.getvalue(), "soportes.zip").status_code == 415
    assert e.subir("ACTIVO", activo, comprimido.getvalue(), "soportes.xlsx").status_code == 415
    assert e.listar() == []


def test_acepta_excel_csv_y_texto_pero_no_los_muestra_en_linea(client):
    e = Escenario(client, "adj-4@example.com")
    activo = e.activo()
    excel = e.subir("ACTIVO", activo, _xlsx(), "movimientos.xlsx")
    assert excel.status_code == 201
    assert excel.json()["previsualizable"] is False
    assert e.subir("ACTIVO", activo, b"fecha;valor\n2025-01-01;100\n", "extracto.csv").status_code == 201
    assert e.subir("ACTIVO", activo, "nota con tilde ñ".encode("utf-8"), "nota.txt").status_code == 201
    descarga = client.get(e.url(f"/adjuntos/{excel.json()['id']}/archivo"), headers=e.h)
    assert descarga.headers["content-disposition"].startswith("attachment")


def test_archivo_demasiado_grande(client, monkeypatch):
    monkeypatch.setattr(servicios_adjuntos, "TAMANO_MAXIMO_ADJUNTO_MB", 0.001)
    e = Escenario(client, "adj-5@example.com")
    activo = e.activo()
    assert e.subir("ACTIVO", activo, PDF + b"0" * 2048, "grande.pdf").status_code == 413
    assert e.listar() == []


def test_el_mismo_archivo_no_se_adjunta_dos_veces_al_mismo_objeto(client):
    e = Escenario(client, "adj-6@example.com")
    a, b = e.activo("Uno"), e.activo("Dos")
    assert e.subir("ACTIVO", a, PDF, "a.pdf").status_code == 201
    repetido = e.subir("ACTIVO", a, PDF, "otro-nombre.pdf")
    assert repetido.status_code == 409
    assert "ya está adjunto" in repetido.json()["detail"]
    assert e.subir("ACTIVO", b, PDF, "a.pdf").status_code == 201


def test_se_puede_adjuntar_a_cada_tipo_de_objeto(client):
    e = Escenario(client, "adj-7@example.com")
    objetos = {
        "CONTRIBUYENTE": e.cid,
        "PERIODO_FISCAL": e.pid,
        "ACTIVO": e.activo(),
        "FUENTE_INGRESO": e.fuente(),
        "DOCUMENTO_SOPORTE": e.documento(),
        "PROVEEDOR": e.proveedor(),
        "MOVIMIENTO": e.movimiento(),
    }
    for indice, (tipo, entidad_id) in enumerate(objetos.items()):
        r = e.subir(tipo, entidad_id, PDF + str(indice).encode(), f"{tipo}.pdf")
        assert r.status_code == 201, (tipo, r.text)
        assert r.json()["etiqueta_entidad"]
    assert len(e.listar()) == len(objetos)

    resumen = client.get(e.url("/adjuntos/resumen"), headers=e.h).json()
    assert {(c["entidad_tipo"], c["entidad_id"]): c["total"] for c in resumen} == {
        (tipo, entidad_id): 1 for tipo, entidad_id in objetos.items()
    }


def test_objeto_inexistente_o_de_otro_contribuyente(client):
    e = Escenario(client, "adj-8@example.com")
    ajeno = Escenario(client, "adj-8b@example.com")
    activo_ajeno = ajeno.activo()
    assert e.subir("ACTIVO", 999999).status_code == 404
    assert e.subir("ACTIVO", activo_ajeno).status_code == 404
    assert e.subir("CONTRIBUYENTE", e.cid + 999).status_code == 404
    assert e.subir("PERIODO_FISCAL", ajeno.pid).status_code == 404
    assert e.subir("INVENTADO", 1).status_code == 422


def test_un_contador_no_ve_ni_toca_los_adjuntos_de_otro(client):
    e = Escenario(client, "adj-9@example.com")
    otro = _registrar(client, "adj-9b@example.com")
    adjunto = e.subir("ACTIVO", e.activo()).json()
    base = e.url("/adjuntos")
    assert client.get(base, headers=otro).status_code == 404
    assert client.get(f"{base}/resumen", headers=otro).status_code == 404
    assert client.get(f"{base}/{adjunto['id']}/archivo", headers=otro).status_code == 404
    assert client.patch(f"{base}/{adjunto['id']}", json={"descripcion": "x"}, headers=otro).status_code == 404
    assert client.delete(f"{base}/{adjunto['id']}", headers=otro).status_code == 404
    assert client.get(e.url(f"/periodos-fiscales/{e.pid}/soportes/zip"), headers=otro).status_code == 404
    subida = client.post(
        base,
        data={"entidad_tipo": "ACTIVO", "entidad_id": 1},
        files={"archivo": ("a.pdf", PDF)},
        headers=otro,
    )
    assert subida.status_code == 404


def test_un_adjunto_no_se_alcanza_con_el_id_de_otro_contribuyente(client):
    e = Escenario(client, "adj-10@example.com")
    segundo = client.post(
        "/contribuyentes",
        json={"nombre": "Otro", "rut": "2020", "tipo_contribuyente": "ASALARIADO"},
        headers=e.h,
    ).json()["id"]
    adjunto = e.subir("ACTIVO", e.activo()).json()
    assert client.get(f"/contribuyentes/{segundo}/adjuntos/{adjunto['id']}/archivo", headers=e.h).status_code == 404
    assert client.delete(f"/contribuyentes/{segundo}/adjuntos/{adjunto['id']}", headers=e.h).status_code == 404


def test_sin_token_no_hay_acceso(client):
    assert client.get("/contribuyentes/1/adjuntos").status_code == 401
    assert client.post("/contribuyentes/1/adjuntos", files={"archivo": ("a.pdf", PDF)}).status_code in (401, 422)


def test_el_nombre_no_puede_salirse_del_almacen(client):
    e = Escenario(client, "adj-11@example.com")
    r = e.subir("ACTIVO", e.activo(), PNG, "../../../etc/pass wd.png")
    assert r.status_code == 201
    assert r.json()["nombre_original"] == "pass wd.png"
    r2 = e.subir("ACTIVO", e.activo("Otro"), PNG, "..\\..\\windows\\system32\\x.png")
    assert r2.json()["nombre_original"] == "x.png"
    for ruta in Path(servicios_adjuntos.ALMACEN_ADJUNTOS).rglob("*"):
        assert Path(servicios_adjuntos.ALMACEN_ADJUNTOS) in ruta.resolve().parents


def test_nombre_con_tildes_se_descarga(client):
    e = Escenario(client, "adj-12@example.com")
    adjunto = e.subir("ACTIVO", e.activo(), PDF, "Declaración año 2025 ñandú.pdf").json()
    r = client.get(e.url(f"/adjuntos/{adjunto['id']}/archivo"), headers=e.h)
    assert r.status_code == 200
    assert "filename*=" in r.headers["content-disposition"]


def test_editar_descripcion_y_categoria(client):
    e = Escenario(client, "adj-13@example.com")
    adjunto = e.subir("ACTIVO", e.activo(), descripcion="vieja").json()
    r = client.patch(
        e.url(f"/adjuntos/{adjunto['id']}"),
        json={"descripcion": "Transferencia de abril", "categoria": "TRANSFERENCIA"},
        headers=e.h,
    )
    assert r.status_code == 200
    assert r.json()["descripcion"] == "Transferencia de abril"
    assert r.json()["categoria"] == "TRANSFERENCIA"
    solo_categoria = client.patch(e.url(f"/adjuntos/{adjunto['id']}"), json={"categoria": "CAPTURA"}, headers=e.h)
    assert solo_categoria.json()["descripcion"] == "Transferencia de abril"
    vaciada = client.patch(e.url(f"/adjuntos/{adjunto['id']}"), json={"descripcion": "   "}, headers=e.h)
    assert vaciada.json()["descripcion"] is None
    assert client.patch(e.url(f"/adjuntos/{adjunto['id']}"), json={"categoria": "XYZ"}, headers=e.h).status_code == 422


def test_filtros_del_listado(client):
    e = Escenario(client, "adj-14@example.com")
    activo, fuente = e.activo("Casa"), e.fuente()
    e.subir("ACTIVO", activo, PDF, "escritura.pdf", categoria="CONTRATO", descripcion="Notaría 5")
    e.subir("FUENTE_INGRESO", fuente, PNG, "pantallazo.png", categoria="CAPTURA")
    e.subir("CONTRIBUYENTE", e.cid, JPG, "cedula.jpg", categoria="CERTIFICADO")

    assert len(e.listar()) == 3
    assert [a["nombre_original"] for a in e.listar(entidad_tipo="ACTIVO")] == ["escritura.pdf"]
    assert [a["nombre_original"] for a in e.listar(entidad_tipo="ACTIVO", entidad_id=activo)] == ["escritura.pdf"]
    assert e.listar(entidad_tipo="ACTIVO", entidad_id=activo + 999) == []
    assert [a["nombre_original"] for a in e.listar(categoria="CAPTURA")] == ["pantallazo.png"]
    assert [a["nombre_original"] for a in e.listar(q="notaría")] == ["escritura.pdf"]
    assert [a["nombre_original"] for a in e.listar(q="PANTALL")] == ["pantallazo.png"]
    assert e.listar(q="%") == []
    assert {a["nombre_original"] for a in e.listar(periodo_fiscal_id=e.pid)} == {"escritura.pdf", "pantallazo.png"}
    con_generales = e.listar(periodo_fiscal_id=e.pid, incluir_generales=True)
    assert {a["nombre_original"] for a in con_generales} == {"escritura.pdf", "pantallazo.png", "cedula.jpg"}


def test_filtro_por_periodo_incluye_documentos_soporte_del_anio(client):
    e = Escenario(client, "adj-15@example.com")
    otro_pid = e.periodo(2024)
    doc_2025 = e.documento("FV-2025", "2025-06-01")
    doc_2024 = e.documento("FV-2024", "2024-06-01")
    e.subir("DOCUMENTO_SOPORTE", doc_2025, PDF, "f25.pdf")
    e.subir("DOCUMENTO_SOPORTE", doc_2024, PDF, "f24.pdf")
    assert [a["nombre_original"] for a in e.listar(periodo_fiscal_id=e.pid)] == ["f25.pdf"]
    assert [a["nombre_original"] for a in e.listar(periodo_fiscal_id=otro_pid)] == ["f24.pdf"]
    assert client.get(e.url("/adjuntos"), params={"periodo_fiscal_id": 999999}, headers=e.h).status_code == 404


def test_eliminar_un_adjunto_borra_su_archivo(client):
    e = Escenario(client, "adj-16@example.com")
    adjunto = e.subir("ACTIVO", e.activo()).json()
    almacen = Path(servicios_adjuntos.ALMACEN_ADJUNTOS)
    antes = {p for p in almacen.rglob("*") if p.is_file()}
    assert client.delete(e.url(f"/adjuntos/{adjunto['id']}"), headers=e.h).status_code == 204
    despues = {p for p in almacen.rglob("*") if p.is_file()}
    assert len(antes - despues) == 1
    assert client.get(e.url(f"/adjuntos/{adjunto['id']}/archivo"), headers=e.h).status_code == 404
    assert client.delete(e.url(f"/adjuntos/{adjunto['id']}"), headers=e.h).status_code == 404


def test_archivo_perdido_del_almacen_da_404_claro(client):
    e = Escenario(client, "adj-17@example.com")
    adjunto = e.subir("ACTIVO", e.activo()).json()
    almacen = Path(servicios_adjuntos.ALMACEN_ADJUNTOS) / str(e.cid)
    for archivo in almacen.iterdir():
        os.remove(archivo)
    r = client.get(e.url(f"/adjuntos/{adjunto['id']}/archivo"), headers=e.h)
    assert r.status_code == 404
    assert "almacén" in r.json()["detail"]


def test_eliminar_activo_o_fuente_borra_sus_adjuntos(client):
    e = Escenario(client, "adj-18@example.com")
    activo, fuente = e.activo(), e.fuente()
    e.subir("ACTIVO", activo, PDF, "a.pdf")
    e.subir("FUENTE_INGRESO", fuente, PNG, "f.png")
    conservado = e.subir("CONTRIBUYENTE", e.cid, JPG, "c.jpg").json()
    almacen = Path(servicios_adjuntos.ALMACEN_ADJUNTOS) / str(e.cid)
    assert len(list(almacen.iterdir())) == 3

    assert client.delete(e.url(f"/activos/{activo}"), headers=e.h).status_code == 204
    assert client.delete(e.url(f"/fuentes-ingreso/{fuente}"), headers=e.h).status_code == 204
    assert [a["id"] for a in e.listar()] == [conservado["id"]]
    assert len(list(almacen.iterdir())) == 1


def test_periodo_cerrado_permite_adjuntar_pero_no_eliminar(client):
    e = Escenario(client, "adj-19@example.com", tipo="ASALARIADO")
    activo = e.activo()
    adjunto = e.subir("ACTIVO", activo).json()
    assert client.post(e.url(f"/periodos-fiscales/{e.pid}/cerrar"), headers=e.h).status_code == 200

    nuevo = e.subir("ACTIVO", activo, PNG, "tardio.png")
    assert nuevo.status_code == 201
    editado = client.patch(e.url(f"/adjuntos/{adjunto['id']}"), json={"descripcion": "ok"}, headers=e.h)
    assert editado.status_code == 200
    bloqueado = client.delete(e.url(f"/adjuntos/{adjunto['id']}"), headers=e.h)
    assert bloqueado.status_code == 409
    assert "cerrado" in bloqueado.json()["detail"]

    client.post(e.url(f"/periodos-fiscales/{e.pid}/reabrir"), headers=e.h)
    assert client.delete(e.url(f"/adjuntos/{adjunto['id']}"), headers=e.h).status_code == 204


def test_el_inventario_del_cierre_no_admite_adjuntos(client):
    e = Escenario(client, "adj-20@example.com", tipo="INDEPENDIENTE")
    client.post(e.url(f"/periodos-fiscales/{e.pid}/cerrar"), headers=e.h)
    inventario = [a for a in client.get(e.url("/activos"), headers=e.h).json() if a["tipo"] == "INVENTARIO"]
    assert inventario
    r = e.subir("ACTIVO", inventario[0]["id"])
    assert r.status_code == 409
    assert "inventario" in r.json()["detail"].lower()


def test_eliminar_contribuyente_sin_datos_borra_sus_documentos(client):
    e = Escenario(client, "adj-21@example.com", tipo="ASALARIADO")
    vacio = client.post(
        "/contribuyentes",
        json={"nombre": "Por error", "rut": "9", "tipo_contribuyente": "ASALARIADO"},
        headers=e.h,
    ).json()["id"]
    client.post(
        f"/contribuyentes/{vacio}/adjuntos",
        data={"entidad_tipo": "CONTRIBUYENTE", "entidad_id": vacio},
        files={"archivo": ("rut.pdf", PDF)},
        headers=e.h,
    )
    almacen = Path(servicios_adjuntos.ALMACEN_ADJUNTOS) / str(vacio)
    assert len(list(almacen.iterdir())) == 1
    assert client.delete(f"/contribuyentes/{vacio}", headers=e.h).status_code == 204
    assert list(almacen.iterdir()) == []


def test_zip_de_soportes_del_anio(client):
    e = Escenario(client, "adj-22@example.com")
    activo = e.activo("Apartamento / Chapinero")
    e.subir("ACTIVO", activo, PDF, "recibo.pdf", categoria="RECIBO", descripcion="Predial")
    e.subir("ACTIVO", activo, PDF + b"2", "recibo.pdf")
    e.subir("CONTRIBUYENTE", e.cid, JPG, "cedula.jpg")
    e.subir("PERIODO_FISCAL", e.pid, PDF + b"3", "declaracion-presentada.pdf", categoria="DECLARACION")
    otro_pid = e.periodo(2024)
    fuente_2024 = client.post(
        e.url("/fuentes-ingreso"),
        json={"concepto": "Salario 2024", "valor_anual": 1, "periodo_fiscal_id": otro_pid},
        headers=e.h,
    ).json()["id"]
    e.subir("FUENTE_INGRESO", fuente_2024, PNG, "otro-anio.png")

    r = client.get(e.url(f"/periodos-fiscales/{e.pid}/soportes/zip"), headers=e.h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "soportes_1010_2025.zip" in r.headers["content-disposition"]
    assert int(r.headers["content-length"]) == len(r.content)

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert z.testzip() is None
        nombres = set(z.namelist())
        assert nombres == {
            "Activos/Apartamento _ Chapinero/recibo.pdf",
            "Activos/Apartamento _ Chapinero/recibo (2).pdf",
            "General/cedula.jpg",
            "Declaración del año/declaracion-presentada.pdf",
            "indice.csv",
        }
        assert z.read("General/cedula.jpg") == JPG
        filas = list(csv.reader(io.StringIO(z.read("indice.csv").decode("utf-8-sig"))))
        assert filas[0][0] == "Archivo en el ZIP"
        assert len(filas) == 5
        assert any("Predial" in fila[3] for fila in filas[1:])


def test_zip_sin_soportes_trae_solo_el_indice(client):
    e = Escenario(client, "adj-23@example.com")
    r = client.get(e.url(f"/periodos-fiscales/{e.pid}/soportes/zip"), headers=e.h)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert z.namelist() == ["indice.csv"]


def test_las_acciones_sobre_adjuntos_quedan_auditadas(client):
    e = Escenario(client, "adj-24@example.com")
    adjunto = e.subir("ACTIVO", e.activo()).json()
    client.patch(e.url(f"/adjuntos/{adjunto['id']}"), json={"descripcion": "x"}, headers=e.h)
    client.get(e.url(f"/periodos-fiscales/{e.pid}/soportes/zip"), headers=e.h)
    client.delete(e.url(f"/adjuntos/{adjunto['id']}"), headers=e.h)
    eventos = client.get("/auditoria", headers=e.h)
    acciones = {ev["accion"] for ev in eventos.json()}
    assert {"subir_adjunto", "actualizar_adjunto", "descargar_soportes", "eliminar_adjunto"} <= acciones
