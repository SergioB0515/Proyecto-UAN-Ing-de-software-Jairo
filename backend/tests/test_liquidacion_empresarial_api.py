"""Pruebas de la API de la parte empresarial.

Lo que el motor no puede probar solo: que el costo de ventas del inventario
llegue a la liquidación, que la depreciación se persista y se recalcule, que
las pérdidas vivan por contribuyente y no por periodo, y que las facilidades
no arrastren cifras del año anterior.
"""

from decimal import Decimal as D

from .test_movimientos import Escenario


def _token(client, email: str) -> dict:
    client.post(
        "/contadores/registro",
        json={"nombre": "Contador", "email": email, "contrasena": "claveDePrueba1"},
    )
    login = client.post(
        "/contadores/login", data={"username": email, "password": "claveDePrueba1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _base(cid, pid):
    return f"/liquidacion/contribuyentes/{cid}/periodos-fiscales/{pid}"


def _valor(liq, codigo):
    return D(next((r["valor"] for r in liq["renglones"] if r["codigo"] == codigo), "0"))


def _activo(client, h, cid, pid, descripcion, valor, tipo="VEHICULO"):
    return client.post(
        f"/contribuyentes/{cid}/activos",
        json={"descripcion": descripcion, "tipo": tipo, "valor": valor,
              "periodo_fiscal_id": pid},
        headers=h,
    ).json()["id"]


# ---------------------------------------------------------------------------
# Costo de ventas: el hueco que motivó todo esto
# ---------------------------------------------------------------------------


def test_el_costo_de_ventas_del_inventario_llega_a_la_liquidacion(client):
    e = Escenario(client, "emp-cv1@example.com")
    pid = e.periodos[2025]
    producto = e.producto()
    e.compras_y_venta(producto)
    client.post(
        f"/contribuyentes/{e.cid}/fuentes-ingreso",
        json={"concepto": "Venta de mercancía", "valor_anual": 3000, "periodo_fiscal_id": pid},
        headers=e.h,
    )

    liq = client.get(_base(e.cid, pid), headers=e.h).json()

    # PEPS: 10 × 100 + 5 × 120 = 1.600 de costo por las 15 unidades vendidas.
    assert _valor(liq, "CG-COSTO-VENTAS") == D("1600.00")
    assert _valor(liq, "CG-INGRESOS") == D("3000.00")
    assert _valor(liq, "CG-RL-ANTES") == D("1400.00")


def test_un_asalariado_no_arrastra_costo_de_ventas(client):
    h = _token(client, "emp-cv2@example.com")
    cid = client.post(
        "/contribuyentes",
        json={"nombre": "Asalariado", "rut": "1", "tipo_contribuyente": "ASALARIADO"},
        headers=h,
    ).json()["id"]
    pid = client.post(
        f"/contribuyentes/{cid}/periodos-fiscales", json={"anio_gravable": 2025}, headers=h
    ).json()["id"]

    liq = client.get(_base(cid, pid), headers=h).json()

    assert _valor(liq, "CG-COSTO-VENTAS") == D("0")


# ---------------------------------------------------------------------------
# Depreciación
# ---------------------------------------------------------------------------


def test_la_depreciacion_se_guarda_y_devuelve_calculada(client):
    h = _token(client, "emp-dep1@example.com")
    cid = client.post(
        "/contribuyentes",
        json={"nombre": "Comerciante", "rut": "2", "tipo_contribuyente": "INDEPENDIENTE"},
        headers=h,
    ).json()["id"]
    pid = client.post(
        f"/contribuyentes/{cid}/periodos-fiscales", json={"anio_gravable": 2025}, headers=h
    ).json()["id"]
    aid = _activo(client, h, cid, pid, "Camioneta", 120000000)

    guardado = client.put(
        f"{_base(cid, pid)}/depreciacion",
        json=[{"activo_id": aid, "categoria": "FLOTA_Y_EQUIPO_DE_TRANSPORTE_TERRESTRE",
               "vida_util_anios": 10, "valor_residual": "0"}],
        headers=h,
    )

    assert guardado.status_code == 200
    fila = guardado.json()[0]
    assert D(fila["depreciacion_del_periodo"]) == D("12000000.00")
    assert D(fila["tasa_maxima_art_137"]) == D("0.1000")
    assert "art. 137" in fila["formula"] or "÷ 10 años" in fila["formula"]

    liq = client.get(_base(cid, pid), headers=h).json()
    assert _valor(liq, "DEP-TOTAL") == D("12000000.00")


def test_la_depreciacion_de_un_activo_ajeno_se_rechaza(client):
    h = _token(client, "emp-dep2@example.com")
    cid_a = client.post("/contribuyentes", json={"nombre": "A", "rut": "3",
                        "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    pid_a = client.post(f"/contribuyentes/{cid_a}/periodos-fiscales",
                        json={"anio_gravable": 2025}, headers=h).json()["id"]
    cid_b = client.post("/contribuyentes", json={"nombre": "B", "rut": "4",
                        "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    pid_b = client.post(f"/contribuyentes/{cid_b}/periodos-fiscales",
                        json={"anio_gravable": 2025}, headers=h).json()["id"]
    aid_b = _activo(client, h, cid_b, pid_b, "Equipo", 10000000)

    respuesta = client.put(
        f"{_base(cid_a, pid_a)}/depreciacion",
        json=[{"activo_id": aid_b, "categoria": "MAQUINARIA_Y_EQUIPOS", "vida_util_anios": 10}],
        headers=h,
    )

    assert respuesta.status_code == 404


def test_el_catalogo_de_categorias_trae_la_tasa_y_la_vida_util_equivalente(client):
    h = _token(client, "emp-dep3@example.com")
    catalogo = client.get(
        "/liquidacion/categorias-depreciacion?anio_gravable=2025", headers=h
    ).json()
    por_valor = {c["valor"]: c for c in catalogo}
    assert len(catalogo) == 16
    assert D(por_valor["CONSTRUCCIONES_Y_EDIFICACIONES"]["tasa_maxima_anual"]) == D("0.0222")
    assert D(por_valor["EQUIPO_DE_COMPUTACION"]["tasa_maxima_anual"]) == D("0.2000")


def test_la_depreciacion_se_puede_quitar(client):
    h = _token(client, "emp-dep4@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "C", "rut": "5",
                      "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]
    aid = _activo(client, h, cid, pid, "Equipo", 10000000)
    client.put(f"{_base(cid, pid)}/depreciacion",
               json=[{"activo_id": aid, "categoria": "MAQUINARIA_Y_EQUIPOS",
                      "vida_util_anios": 10}], headers=h)

    borrado = client.delete(f"{_base(cid, pid)}/depreciacion/{aid}", headers=h)

    assert borrado.status_code == 204
    assert client.get(f"{_base(cid, pid)}/depreciacion", headers=h).json() == []


# ---------------------------------------------------------------------------
# Pérdidas fiscales
# ---------------------------------------------------------------------------


def test_las_perdidas_viven_por_contribuyente_y_marcan_su_vigencia(client):
    h = _token(client, "emp-per1@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "D", "rut": "6",
                      "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    client.post(f"/liquidacion/contribuyentes/{cid}/perdidas?anio_gravable=2025",
                json={"anio_origen": 2023, "tipo_renta": "NO_LABORAL", "valor": "20000000"},
                headers=h)
    client.post(f"/liquidacion/contribuyentes/{cid}/perdidas?anio_gravable=2025",
                json={"anio_origen": 2010, "tipo_renta": "NO_LABORAL", "valor": "5000000"},
                headers=h)

    listado = client.get(
        f"/liquidacion/contribuyentes/{cid}/perdidas?anio_gravable=2025", headers=h
    ).json()

    por_anio = {p["anio_origen"]: p for p in listado}
    assert por_anio[2023]["vigente"] is True
    assert por_anio[2010]["vigente"] is False   # más de 12 periodos
    assert D(por_anio[2023]["saldo_por_compensar"]) == D("20000000.00")


def test_la_perdida_registrada_se_compensa_en_la_liquidacion(client):
    h = _token(client, "emp-per2@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "E", "rut": "7",
                      "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]
    fid = client.post(f"/contribuyentes/{cid}/fuentes-ingreso",
                      json={"concepto": "Venta de mercancía", "valor_anual": 100000000,
                            "periodo_fiscal_id": pid}, headers=h).json()["id"]
    client.put(f"{_base(cid, pid)}/ingresos",
               json=[{"fuente_ingreso_id": fid, "cedula": "NO_LABORAL"}], headers=h)
    client.post(f"/liquidacion/contribuyentes/{cid}/perdidas?anio_gravable=2025",
                json={"anio_origen": 2023, "tipo_renta": "NO_LABORAL", "valor": "30000000"},
                headers=h)

    liq = client.get(_base(cid, pid), headers=h).json()

    assert _valor(liq, "CG-COMPENSACION") == D("30000000.00")
    assert _valor(liq, "CG-RL-ANTES") == D("70000000.00")


def test_una_perdida_de_otro_contribuyente_no_se_borra(client):
    h = _token(client, "emp-per3@example.com")
    cid_a = client.post("/contribuyentes", json={"nombre": "F", "rut": "8",
                        "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    cid_b = client.post("/contribuyentes", json={"nombre": "G", "rut": "9",
                        "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    pid_perdida = client.post(
        f"/liquidacion/contribuyentes/{cid_b}/perdidas?anio_gravable=2025",
        json={"anio_origen": 2023, "tipo_renta": "CAPITAL", "valor": "1000000"},
        headers=h,
    ).json()["id"]

    respuesta = client.delete(
        f"/liquidacion/contribuyentes/{cid_a}/perdidas/{pid_perdida}", headers=h
    )

    assert respuesta.status_code == 404


# ---------------------------------------------------------------------------
# Bancarización
# ---------------------------------------------------------------------------


def test_los_pagos_en_efectivo_marcan_los_que_superan_el_limite_individual(client):
    h = _token(client, "emp-ban1@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "H", "rut": "10",
                      "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]
    client.post(f"{_base(cid, pid)}/pagos-efectivo",
                json={"descripcion": "Compra grande", "valor": "6000000"}, headers=h)
    client.post(f"{_base(cid, pid)}/pagos-efectivo",
                json={"descripcion": "Papelería", "valor": "200000"}, headers=h)

    listado = client.get(f"{_base(cid, pid)}/pagos-efectivo", headers=h).json()

    por_descripcion = {p["descripcion"]: p for p in listado}
    # 100 UVT de 2025 = 4.979.900
    assert por_descripcion["Compra grande"]["supera_limite_individual"] is True
    assert por_descripcion["Papelería"]["supera_limite_individual"] is False

    liq = client.get(_base(cid, pid), headers=h).json()
    assert any("límite individual" in d for d in liq["diagnosticos"])


def test_el_limite_general_del_771_5_se_refleja_en_la_liquidacion(client):
    h = _token(client, "emp-ban2@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "I", "rut": "11",
                      "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]
    fid = client.post(f"/contribuyentes/{cid}/fuentes-ingreso",
                      json={"concepto": "Venta de mercancía", "valor_anual": 200000000,
                            "periodo_fiscal_id": pid}, headers=h).json()["id"]
    client.put(f"{_base(cid, pid)}/ingresos",
               json=[{"fuente_ingreso_id": fid, "cedula": "NO_LABORAL"}], headers=h)
    client.patch(f"{_base(cid, pid)}/hoja",
                 json={"total_pagos_del_anio": "100000000", "pagos_en_efectivo": "80000000"},
                 headers=h)

    liq = client.get(_base(cid, pid), headers=h).json()

    # Sin costos registrados, el 35 % de los costos es 0: se rechaza todo.
    assert _valor(liq, "CG-EFECTIVO-RECHAZADO") == D("80000000.00")
    assert any("771-5" in d for d in liq["diagnosticos"])


# ---------------------------------------------------------------------------
# Facilidades
# ---------------------------------------------------------------------------


def test_el_catalogo_de_plantillas_trae_la_norma_y_el_tope_en_pesos(client):
    h = _token(client, "emp-pla1@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "J", "rut": "12",
                      "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]

    catalogo = client.get(f"{_base(cid, pid)}/plantillas-deducciones", headers=h).json()

    por_codigo = {p["codigo"]: p for p in catalogo}
    vivienda = por_codigo["INTERESES_VIVIENDA"]
    assert vivienda["fuente_legal"] == "Art. 119 ET"
    assert D(vivienda["tope_anual_en_pesos"]) == D("1200") * D("49799")
    assert vivienda["sujeto_a_limite_general"] is True
    # Las que el motor ya calcula vienen marcadas para que no se dupliquen.
    assert por_codigo["COMPRAS_1_PCT"]["lo_calcula_el_motor"] is True


def test_crear_una_deduccion_desde_plantilla_pone_la_norma_sola(client):
    h = _token(client, "emp-pla2@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "K", "rut": "13",
                      "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]

    creada = client.post(
        f"{_base(cid, pid)}/deducciones/desde-plantilla"
        f"?codigo=INTERESES_VIVIENDA&valor=12000000",
        headers=h,
    )

    assert creada.status_code == 201
    assert creada.json()["nombre"] == "Intereses de crédito de vivienda"
    assert creada.json()["fuente_legal"] == "Art. 119 ET"
    assert creada.json()["sujeto_a_limite_general"] is True


def test_una_plantilla_que_el_motor_ya_calcula_no_se_puede_agregar(client):
    """Agregarla la contaría dos veces y bajaría el impuesto de forma indebida."""
    h = _token(client, "emp-pla3@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "L", "rut": "14",
                      "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]

    respuesta = client.post(
        f"{_base(cid, pid)}/deducciones/desde-plantilla?codigo=COMPRAS_1_PCT&valor=100000",
        headers=h,
    )

    assert respuesta.status_code == 422
    assert "dos veces" in respuesta.json()["detail"]


def test_una_plantilla_inexistente_lista_las_disponibles(client):
    h = _token(client, "emp-pla4@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "M", "rut": "15",
                      "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]

    respuesta = client.post(
        f"{_base(cid, pid)}/deducciones/desde-plantilla?codigo=NO_EXISTE&valor=1000",
        headers=h,
    )

    assert respuesta.status_code == 422
    assert "INTERESES_VIVIENDA" in respuesta.json()["detail"]


def test_copiar_la_hoja_trae_la_situacion_pero_no_las_cifras(client):
    """Copiar los pesos del año pasado metería cifras viejas sin que se note."""
    h = _token(client, "emp-cop1@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "N", "rut": "16",
                      "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    pid_2024 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2024}, headers=h).json()["id"]
    pid_2025 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2025}, headers=h).json()["id"]
    client.patch(f"{_base(cid, pid_2024)}/hoja",
                 json={"numero_dependientes": 3, "opta_por_costos_y_gastos": True,
                       "metodo_anticipo": "MENOR", "deudas": "80000000",
                       "go_ingresos": "50000000"},
                 headers=h)

    copiada = client.post(f"{_base(cid, pid_2025)}/hoja/copiar-del-anterior", headers=h)

    assert copiada.status_code == 200
    hoja = copiada.json()
    assert hoja["numero_dependientes"] == 3          # situación: se copia
    assert hoja["opta_por_costos_y_gastos"] is True  # situación: se copia
    assert hoja["metodo_anticipo"] == "MENOR"        # situación: se copia
    assert D(hoja["deudas"]) == D("0")               # cifra: NO se copia
    assert D(hoja["go_ingresos"]) == D("0")          # cifra: NO se copia


def test_copiar_la_hoja_trae_el_impuesto_neto_del_ano_anterior(client):
    """Es el dato que habilita el método del promedio del art. 807."""
    h = _token(client, "emp-cop2@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "O", "rut": "17",
                      "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid_2024 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2024}, headers=h).json()["id"]
    pid_2025 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2025}, headers=h).json()["id"]
    client.post(f"/contribuyentes/{cid}/fuentes-ingreso",
                json={"concepto": "Salario de la empresa", "valor_anual": 200000000,
                      "periodo_fiscal_id": pid_2024}, headers=h)
    client.get(f"{_base(cid, pid_2024)}/hoja", headers=h)

    hoja = client.post(f"{_base(cid, pid_2025)}/hoja/copiar-del-anterior", headers=h).json()

    assert D(hoja["impuesto_neto_anio_anterior"]) > D("0")


def test_copiar_sin_ano_anterior_falla_con_un_mensaje_claro(client):
    h = _token(client, "emp-cop3@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "P", "rut": "18",
                      "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]

    respuesta = client.post(f"{_base(cid, pid)}/hoja/copiar-del-anterior", headers=h)

    assert respuesta.status_code == 422
    assert "2024" in respuesta.json()["detail"]


# ---------------------------------------------------------------------------
# Comparación patrimonial
# ---------------------------------------------------------------------------


def test_el_patrimonio_del_ano_anterior_se_deduce_de_los_activos_registrados(client):
    """Ya está en la aplicación: volver a teclearlo es una oportunidad de error."""
    h = _token(client, "emp-pat1@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "Q", "rut": "19",
                      "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid_2024 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2024}, headers=h).json()["id"]
    pid_2025 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2025}, headers=h).json()["id"]
    _activo(client, h, cid, pid_2024, "Casa", 100000000, tipo="INMUEBLE")
    _activo(client, h, cid, pid_2025, "Casa", 100000000, tipo="INMUEBLE")
    _activo(client, h, cid, pid_2025, "Apartamento nuevo", 400000000, tipo="INMUEBLE")

    liq = client.get(_base(cid, pid_2025), headers=h).json()

    # Incremento de 400M sin rentas que lo expliquen.
    assert _valor(liq, "COMP-PATRIMONIAL") == D("400000000.00")
    assert _valor(liq, "COMP-PATRIMONIAL-GRAVADA") == D("0")
    assert any("NO se incorporó" in d for d in liq["diagnosticos"])


def test_al_aceptarla_la_diferencia_patrimonial_entra_a_la_base(client):
    h = _token(client, "emp-pat2@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "R", "rut": "20",
                      "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid_2024 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2024}, headers=h).json()["id"]
    pid_2025 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2025}, headers=h).json()["id"]
    _activo(client, h, cid, pid_2024, "Casa", 100000000, tipo="INMUEBLE")
    _activo(client, h, cid, pid_2025, "Casa", 300000000, tipo="INMUEBLE")
    client.patch(f"{_base(cid, pid_2025)}/hoja",
                 json={"aceptar_renta_comparacion_patrimonial": True}, headers=h)

    liq = client.get(_base(cid, pid_2025), headers=h).json()

    assert _valor(liq, "COMP-PATRIMONIAL-GRAVADA") == D("200000000.00")
    assert _valor(liq, "BASE-GRAVABLE") == D("200000000.00")


def test_el_patrimonio_anterior_manual_sobrescribe_el_deducido(client):
    h = _token(client, "emp-pat3@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "S", "rut": "21",
                      "tipo_contribuyente": "ASALARIADO"}, headers=h).json()["id"]
    pid_2024 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2024}, headers=h).json()["id"]
    pid_2025 = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                           json={"anio_gravable": 2025}, headers=h).json()["id"]
    _activo(client, h, cid, pid_2024, "Casa", 100000000, tipo="INMUEBLE")
    _activo(client, h, cid, pid_2025, "Casa", 300000000, tipo="INMUEBLE")
    client.patch(f"{_base(cid, pid_2025)}/hoja",
                 json={"patrimonio_liquido_anterior_manual": "250000000"}, headers=h)

    liq = client.get(_base(cid, pid_2025), headers=h).json()

    assert _valor(liq, "COMP-PATRIMONIAL") == D("50000000.00")


# ---------------------------------------------------------------------------
# Auditoría y aislamiento
# ---------------------------------------------------------------------------


def test_las_decisiones_empresariales_quedan_auditadas(client):
    h = _token(client, "emp-aud1@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "T", "rut": "22",
                      "tipo_contribuyente": "INDEPENDIENTE"}, headers=h).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h).json()["id"]
    aid = _activo(client, h, cid, pid, "Equipo", 10000000)
    client.put(f"{_base(cid, pid)}/depreciacion",
               json=[{"activo_id": aid, "categoria": "MAQUINARIA_Y_EQUIPOS",
                      "vida_util_anios": 10}], headers=h)
    client.post(f"/liquidacion/contribuyentes/{cid}/perdidas?anio_gravable=2025",
                json={"anio_origen": 2023, "tipo_renta": "NO_LABORAL", "valor": "100"},
                headers=h)
    client.post(f"{_base(cid, pid)}/pagos-efectivo",
                json={"descripcion": "Pago", "valor": "100"}, headers=h)

    acciones = [e["accion"] for e in client.get("/auditoria", headers=h).json()]

    assert "guardar_depreciacion" in acciones
    assert "crear_perdida" in acciones
    assert "crear_pago_efectivo" in acciones


def test_un_contador_no_alcanza_lo_empresarial_de_otro(client):
    h_a = _token(client, "emp-ais1a@example.com")
    h_b = _token(client, "emp-ais1b@example.com")
    cid = client.post("/contribuyentes", json={"nombre": "U", "rut": "23",
                      "tipo_contribuyente": "INDEPENDIENTE"}, headers=h_a).json()["id"]
    pid = client.post(f"/contribuyentes/{cid}/periodos-fiscales",
                      json={"anio_gravable": 2025}, headers=h_a).json()["id"]

    assert client.get(f"{_base(cid, pid)}/depreciacion", headers=h_b).status_code == 404
    assert client.get(f"{_base(cid, pid)}/pagos-efectivo", headers=h_b).status_code == 404
    assert client.get(
        f"/liquidacion/contribuyentes/{cid}/perdidas?anio_gravable=2025", headers=h_b
    ).status_code == 404
