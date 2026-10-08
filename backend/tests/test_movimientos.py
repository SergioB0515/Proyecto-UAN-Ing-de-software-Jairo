"""Pruebas del módulo de movimientos: proveedores (HU-13), documentos
soporte y movimientos (HU-12), kardex y costo de ventas (HU-14)."""
from modulos.contribuyentes.modelos import EstadoPeriodo, PeriodoFiscal


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
    """Contador + contribuyente con negocio + periodo 2025 + documento
    soporte + proveedor, listos para registrar movimientos."""

    def __init__(self, client, email: str, tipo: str = "INDEPENDIENTE"):
        self.client = client
        self.token = _crear_contador_y_token(client, email)
        self.h = _headers(self.token)
        self.cid = client.post(
            "/contribuyentes",
            json={"nombre": "Tienda", "rut": "7000000000", "tipo_contribuyente": tipo},
            headers=self.h,
        ).json()["id"]
        self.periodos = {}
        if tipo != "ASALARIADO":
            self.periodo(2025)
            self.documento_id = self.documento("FV-1")
            self.proveedor_id = client.post(
                f"/contribuyentes/{self.cid}/proveedores",
                json={"nombre": "Mayorista", "tipo_persona": "JURIDICA", "identificacion": "900555666"},
                headers=self.h,
            ).json()["id"]

    def periodo(self, anio: int) -> int:
        self.periodos[anio] = self.client.post(
            f"/contribuyentes/{self.cid}/periodos-fiscales",
            json={"anio_gravable": anio},
            headers=self.h,
        ).json()["id"]
        return self.periodos[anio]

    def documento(self, numero: str, tipo: str = "FACTURA") -> int:
        return self.client.post(
            f"/contribuyentes/{self.cid}/documentos-soporte",
            json={"tipo": tipo, "numero": numero, "fecha": "2025-01-01"},
            headers=self.h,
        ).json()["id"]

    def producto(self, codigo: str = "P-001", metodo: str = "PEPS") -> int:
        return self.client.post(
            f"/contribuyentes/{self.cid}/productos",
            json={
                "codigo": codigo,
                "nombre": f"Producto {codigo}",
                "clasificacion_iva": "GRAVADO",
                "metodo_costeo": metodo,
            },
            headers=self.h,
        ).json()["id"]

    def movimiento(self, producto_id, tipo, cantidad, valor_unitario, fecha, anio=2025, **extra):
        datos = {
            "tipo": tipo,
            "producto_id": producto_id,
            "periodo_fiscal_id": self.periodos[anio],
            "documento_soporte_id": self.documento_id,
            "fecha": fecha,
            "cantidad": cantidad,
            "valor_unitario": valor_unitario,
        }
        datos.update(extra)
        return self.client.post(
            f"/contribuyentes/{self.cid}/movimientos", json=datos, headers=self.h
        )

    def compras_y_venta(self, producto_id):
        """10 a 100, 10 a 120, y una venta de 15 a 200."""
        self.movimiento(producto_id, "ENTRADA", 10, 100, "2025-01-10", proveedor_id=self.proveedor_id)
        self.movimiento(producto_id, "ENTRADA", 10, 120, "2025-02-10")
        return self.movimiento(producto_id, "SALIDA", 15, 200, "2025-03-10")


# ------------------------------------------------------------------ Proveedores


def test_crear_y_listar_proveedores(client):
    e = Escenario(client, "mov-prov1@example.com")
    listado = client.get(f"/contribuyentes/{e.cid}/proveedores", headers=e.h)
    assert listado.status_code == 200
    assert listado.json()[0]["identificacion"] == "900555666"


def test_proveedor_con_identificacion_duplicada_falla(client):
    e = Escenario(client, "mov-prov2@example.com")
    respuesta = client.post(
        f"/contribuyentes/{e.cid}/proveedores",
        json={"nombre": "Otro nombre", "tipo_persona": "NATURAL", "identificacion": "900555666"},
        headers=e.h,
    )
    assert respuesta.status_code == 409


def test_proveedor_exige_tipo_de_persona_valido(client):
    e = Escenario(client, "mov-prov3@example.com")
    respuesta = client.post(
        f"/contribuyentes/{e.cid}/proveedores",
        json={"nombre": "X", "tipo_persona": "EMPRESA", "identificacion": "1"},
        headers=e.h,
    )
    assert respuesta.status_code == 422


def test_asalariado_no_tiene_proveedores(client):
    e = Escenario(client, "mov-prov4@example.com", tipo="ASALARIADO")
    respuesta = client.post(
        f"/contribuyentes/{e.cid}/proveedores",
        json={"nombre": "X", "tipo_persona": "NATURAL", "identificacion": "1"},
        headers=e.h,
    )
    assert respuesta.status_code == 409


# ---------------------------------------------------------- Documentos soporte


def test_documento_soporte_duplicado_falla(client):
    e = Escenario(client, "mov-doc1@example.com")
    respuesta = client.post(
        f"/contribuyentes/{e.cid}/documentos-soporte",
        json={"tipo": "FACTURA", "numero": "FV-1", "fecha": "2025-01-01"},
        headers=e.h,
    )
    assert respuesta.status_code == 409


# ------------------------------------------------------------------ Movimientos


def test_entrada_y_salida_actualizan_el_stock(client):
    e = Escenario(client, "mov-1@example.com")
    pid = e.producto()

    entrada = e.movimiento(pid, "ENTRADA", 10, 1500, "2025-01-15", proveedor_id=e.proveedor_id)
    assert entrada.status_code == 201
    # valor_total es derivado: cantidad x valor_unitario.
    assert entrada.json()["valor_total"] == 15000

    salida = e.movimiento(pid, "SALIDA", 4, 2500, "2025-01-20")
    assert salida.status_code == 201

    producto = client.get(f"/contribuyentes/{e.cid}/productos/{pid}", headers=e.h)
    assert producto.json()["stock_actual"] == 6

    listado = client.get(f"/contribuyentes/{e.cid}/movimientos?producto_id={pid}", headers=e.h)
    assert [m["tipo"] for m in listado.json()] == ["ENTRADA", "SALIDA"]


def test_salida_sin_stock_suficiente_falla(client):
    e = Escenario(client, "mov-2@example.com")
    pid = e.producto()
    e.movimiento(pid, "ENTRADA", 3, 100, "2025-01-15")

    respuesta = e.movimiento(pid, "SALIDA", 5, 200, "2025-01-20")
    assert respuesta.status_code == 409

    producto = client.get(f"/contribuyentes/{e.cid}/productos/{pid}", headers=e.h)
    assert producto.json()["stock_actual"] == 3


def test_salida_con_fecha_anterior_a_la_entrada_falla(client):
    # El stock total alcanzaría, pero a esa fecha la mercancía no había
    # entrado todavía.
    e = Escenario(client, "mov-3@example.com")
    pid = e.producto()
    e.movimiento(pid, "ENTRADA", 10, 100, "2025-06-01")

    respuesta = e.movimiento(pid, "SALIDA", 2, 200, "2025-05-01")
    assert respuesta.status_code == 409


def test_movimiento_sin_documento_soporte_falla(client):
    e = Escenario(client, "mov-4@example.com")
    pid = e.producto()
    datos = {
        "tipo": "ENTRADA",
        "producto_id": pid,
        "periodo_fiscal_id": e.periodos[2025],
        "fecha": "2025-01-15",
        "cantidad": 1,
        "valor_unitario": 100,
    }
    respuesta = client.post(f"/contribuyentes/{e.cid}/movimientos", json=datos, headers=e.h)
    assert respuesta.status_code == 422


def test_movimiento_con_documento_de_otro_contribuyente_falla(client):
    e = Escenario(client, "mov-5@example.com")
    otro = Escenario(client, "mov-5b@example.com")
    pid = e.producto()

    respuesta = e.movimiento(
        pid, "ENTRADA", 1, 100, "2025-01-15", documento_soporte_id=otro.documento_id
    )
    assert respuesta.status_code == 404


def test_movimiento_con_fecha_fuera_del_periodo_falla(client):
    e = Escenario(client, "mov-6@example.com")
    pid = e.producto()
    respuesta = e.movimiento(pid, "ENTRADA", 1, 100, "2024-12-31")
    assert respuesta.status_code == 422


def test_salida_con_proveedor_falla(client):
    e = Escenario(client, "mov-7@example.com")
    pid = e.producto()
    e.movimiento(pid, "ENTRADA", 5, 100, "2025-01-15")

    respuesta = e.movimiento(pid, "SALIDA", 1, 200, "2025-01-20", proveedor_id=e.proveedor_id)
    assert respuesta.status_code == 422


def test_movimiento_de_producto_inactivo_falla(client):
    e = Escenario(client, "mov-8@example.com")
    pid = e.producto()
    client.patch(f"/contribuyentes/{e.cid}/productos/{pid}", json={"activo": False}, headers=e.h)

    respuesta = e.movimiento(pid, "ENTRADA", 1, 100, "2025-01-15")
    assert respuesta.status_code == 409


def test_movimiento_en_periodo_cerrado_falla(client, session):
    e = Escenario(client, "mov-9@example.com")
    pid = e.producto()
    # El cierre de periodo es del Incremento 5: aquí se simula directo en BD.
    periodo = session.get(PeriodoFiscal, e.periodos[2025])
    periodo.estado = EstadoPeriodo.CERRADO
    session.add(periodo)
    session.flush()

    respuesta = e.movimiento(pid, "ENTRADA", 1, 100, "2025-01-15")
    assert respuesta.status_code == 409


def test_un_contador_no_ve_movimientos_de_otro(client):
    e = Escenario(client, "mov-10a@example.com")
    token_b = _crear_contador_y_token(client, "mov-10b@example.com")
    respuesta = client.get(f"/contribuyentes/{e.cid}/movimientos", headers=_headers(token_b))
    assert respuesta.status_code == 404


def test_no_se_cambia_el_metodo_de_costeo_con_movimientos(client):
    e = Escenario(client, "mov-11@example.com")
    pid = e.producto(metodo="PEPS")

    # Sin movimientos todavía se puede cambiar.
    cambio = client.patch(
        f"/contribuyentes/{e.cid}/productos/{pid}",
        json={"metodo_costeo": "PROMEDIO_PONDERADO"},
        headers=e.h,
    )
    assert cambio.status_code == 200

    e.movimiento(pid, "ENTRADA", 1, 100, "2025-01-15")
    cambio = client.patch(
        f"/contribuyentes/{e.cid}/productos/{pid}",
        json={"metodo_costeo": "PEPS"},
        headers=e.h,
    )
    assert cambio.status_code == 409


# --------------------------------------------------- Kardex y costo de ventas


def test_kardex_peps(client):
    e = Escenario(client, "mov-12@example.com")
    pid = e.producto(metodo="PEPS")
    assert e.compras_y_venta(pid).status_code == 201

    kardex = client.get(f"/contribuyentes/{e.cid}/productos/{pid}/kardex", headers=e.h)
    assert kardex.status_code == 200
    cuerpo = kardex.json()
    assert len(cuerpo["lineas"]) == 3
    assert cuerpo["lineas"][-1]["costo_total"] == 1600  # 10x100 + 5x120
    assert cuerpo["saldo_cantidad"] == 5
    assert cuerpo["saldo_valor"] == 600


def test_kardex_promedio_ponderado(client):
    e = Escenario(client, "mov-13@example.com")
    pid = e.producto(metodo="PROMEDIO_PONDERADO")
    e.compras_y_venta(pid)

    cuerpo = client.get(f"/contribuyentes/{e.cid}/productos/{pid}/kardex", headers=e.h).json()
    assert cuerpo["lineas"][-1]["costo_unitario"] == 110
    assert cuerpo["lineas"][-1]["costo_total"] == 1650
    assert cuerpo["saldo_valor"] == 550


def test_costo_de_ventas_del_periodo(client):
    e = Escenario(client, "mov-14@example.com")
    peps = e.producto("P-PEPS", "PEPS")
    promedio = e.producto("P-PROM", "PROMEDIO_PONDERADO")
    e.compras_y_venta(peps)
    e.compras_y_venta(promedio)

    respuesta = client.get(
        f"/contribuyentes/{e.cid}/periodos-fiscales/{e.periodos[2025]}/costo-ventas",
        headers=e.h,
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["anio_gravable"] == 2025
    por_codigo = {p["codigo"]: p for p in cuerpo["productos"]}
    assert por_codigo["P-PEPS"]["costo_ventas"] == 1600
    assert por_codigo["P-PROM"]["costo_ventas"] == 1650
    assert por_codigo["P-PEPS"]["ingresos_ventas"] == 3000
    assert cuerpo["total_costo_ventas"] == 3250
    assert cuerpo["total_ingresos_ventas"] == 6000
    assert cuerpo["total_utilidad_bruta"] == 2750
    assert cuerpo["total_inventario_final"] == 1150  # 600 + 550


def test_costo_de_ventas_arrastra_el_saldo_del_anio_anterior(client):
    e = Escenario(client, "mov-15@example.com")
    e.periodo(2026)
    pid = e.producto()
    e.movimiento(pid, "ENTRADA", 10, 100, "2025-11-01", anio=2025)
    e.movimiento(pid, "SALIDA", 4, 150, "2026-02-01", anio=2026)

    url = f"/contribuyentes/{e.cid}/periodos-fiscales/{{}}/costo-ventas"
    cierre_2025 = client.get(url.format(e.periodos[2025]), headers=e.h).json()
    assert cierre_2025["total_costo_ventas"] == 0
    assert cierre_2025["total_inventario_final"] == 1000

    cierre_2026 = client.get(url.format(e.periodos[2026]), headers=e.h).json()
    assert cierre_2026["total_costo_ventas"] == 400
    assert cierre_2026["total_inventario_final"] == 600
