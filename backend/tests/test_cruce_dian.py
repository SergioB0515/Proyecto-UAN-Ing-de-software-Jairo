"""El cruce de la liquidación contra lo que la DIAN ya sabe."""

from decimal import Decimal as D

from modulos.conciliacion.cruce import (
    ALTA,
    MEDIA,
    OK,
    OPORTUNIDAD,
    CifrasDeclaradas,
    Registro,
    comparar,
    cruzar,
    cuadrar_topes,
)

from .test_exogena import (
    _crear_contador_y_token,
    _crear_contribuyente_con_periodo,
    _headers,
    _subir_fixture,
)

UVT = D("49799")


def _avaluo(valor, participacion="100.00"):
    return Registro(
        "Valor avalúo catastral (Concepto: 1476)", D(valor),
        "Tope 2: Patrimonio | R29 Patrimonio Bruto",
        f"Porcentaje de Participación: {participacion} | Matricula: X",
        "R29",
    )


def _declarado_anterior(valor):
    return Registro(
        "Total patrimonio bruto declarado en el año anterior", D(valor),
        "El Tope 2 - Patrimonio, toma el mayor valor entre la suma de variables del "
        "año gravable reportadas en la exógena y el valor de patrimonio bruto "
        "declarado en el año anterior",
        es_auto_reportado=True,
    )


def _por_clave(comparaciones):
    return {c.clave: c for c in comparaciones}


# ---------------------------------------------------------------------------
# Los topes se reconstruyen desde el detalle
# ---------------------------------------------------------------------------


def test_el_tope_de_patrimonio_es_el_mayor_entre_el_detalle_y_lo_declarado_antes():
    registros = [_avaluo("100000000"), _declarado_anterior("150000000")]
    [tope] = cuadrar_topes(registros, {"Tope 2 - Patrimonio": D("150000000")})
    assert tope.cuadra
    assert tope.suma_detalle == D("100000000")
    assert tope.piso == D("150000000")
    assert "año anterior" in tope.explicacion

    registros = [_avaluo("200000000"), _declarado_anterior("150000000")]
    [tope] = cuadrar_topes(registros, {"Tope 2 - Patrimonio": D("200000000")})
    assert tope.cuadra


def test_un_bien_en_copropiedad_cuenta_por_su_participacion():
    """Deducido de un archivo real: con los avalúos completos el detalle
    superaba el tope, cosa imposible si el tope es el mayor de los dos valores.
    """
    registros = [_avaluo("200000000", "50.00"), _avaluo("80000000"),
                 _declarado_anterior("100000000")]
    [tope] = cuadrar_topes(registros, {"Tope 2 - Patrimonio": D("180000000")})
    assert tope.suma_detalle == D("180000000")
    assert tope.cuadra
    assert tope.registros[0].valor_propio == D("100000000")


def test_un_tope_que_no_se_puede_reconstruir_se_dice():
    resultado = cruzar(
        [Registro("Consumos", D("500000"), "Tope 3: Consumos TC")],
        {"Tope 3 - Consumo TC": D("900000")},
        CifrasDeclaradas({}, uvt=UVT),
    )
    assert not resultado.topes[0].cuadra
    assert "No cuadra" in resultado.topes[0].explicacion
    assert any("No se pudo reconstruir" in d for d in resultado.diagnosticos)


def test_el_umbral_de_cada_tope_dice_si_obliga_a_declarar():
    [tope] = cuadrar_topes(
        [Registro("Movimientos", D("80000000"), "Tope 4: Consignaciones e inversiones")],
        {"Tope 4 - Movimiento": D("80000000")},
        {4: D("1400") * UVT},
    )
    assert tope.supera_umbral is True


# ---------------------------------------------------------------------------
# Lo declarado frente a lo reportado
# ---------------------------------------------------------------------------


def test_declarar_menos_patrimonio_que_el_tope_es_alerta_alta():
    c = _por_clave(comparar([], {2: D("300000000")},
                            CifrasDeclaradas({29: D("250000000")}, uvt=UVT)))
    assert c["PATRIMONIO"].severidad == ALTA
    assert c["PATRIMONIO"].diferencia == D("-50000000")

    c = _por_clave(comparar([], {2: D("300000000")},
                            CifrasDeclaradas({29: D("320000000")}, uvt=UVT)))
    assert c["PATRIMONIO"].severidad == OK


def test_los_ingresos_suman_todas_las_cedulas_y_la_ganancia_ocasional():
    declarado = CifrasDeclaradas(
        {32: D("40000000"), 74: D("30000000"), 112: D("50000000")}, uvt=UVT
    )
    c = _por_clave(comparar([], {1: D("120000000")}, declarado))
    assert c["INGRESOS"].valor_declarado == D("120000000")
    assert c["INGRESOS"].severidad == OK


def test_las_retenciones_de_mas_piden_certificado_y_las_de_menos_son_plata_perdida():
    reportada = Registro("Retención practicada", D("900000"),
                         "R132 Retenciones año gravable a declarar", "", "R132")
    de_mas = _por_clave(comparar([reportada], {},
                                 CifrasDeclaradas({132: D("2000000")}, uvt=UVT)))
    assert de_mas["RETENCIONES"].severidad == MEDIA
    assert "certificado" in de_mas["RETENCIONES"].mensaje

    de_menos = _por_clave(comparar([reportada], {},
                                   CifrasDeclaradas({132: D("0")}, uvt=UVT)))
    assert de_menos["RETENCIONES"].severidad == OPORTUNIDAD
    assert de_menos["RETENCIONES"].diferencia == D("-900000")


def test_las_compras_con_factura_electronica_sin_registrar_son_una_oportunidad():
    beneficio = Registro(
        "Monto total de facturación electrónica susceptible de beneficio", D("30000000")
    )
    c = _por_clave(comparar([beneficio], {}, CifrasDeclaradas({}, uvt=UVT)))
    assert c["COMPRAS_FE"].severidad == OPORTUNIDAD
    assert "$300.000" in c["COMPRAS_FE"].mensaje          # 1 % de 30.000.000

    de_mas = _por_clave(comparar(
        [beneficio], {},
        CifrasDeclaradas({}, compras_con_factura_electronica=D("50000000"), uvt=UVT),
    ))
    assert de_mas["COMPRAS_FE"].severidad == MEDIA


def test_un_registro_condicional_no_entra_en_ninguna_comparacion():
    condicional = Registro(
        "Adquisición de bienes reportada en notaría", D("80000000"),
        "Según el bien o derecho reportado se puede usar en renglones como R112, R29",
        "", "R112, R29", renglones_son_condicionales=True,
    )
    resultado = cruzar([condicional], {}, CifrasDeclaradas({}, uvt=UVT))
    assert "GANANCIA_OCASIONAL" not in _por_clave(resultado.comparaciones)
    assert len(resultado.pendientes) == 1


def test_gastar_mas_de_lo_que_se_declara_ganar_es_un_indicio_no_un_error():
    c = _por_clave(comparar(
        [], {3: D("60000000"), 5: D("20000000")},
        CifrasDeclaradas({32: D("50000000")}, uvt=UVT),
    ))
    assert c["INDICIO_GASTO"].severidad == MEDIA
    assert "indicio" in c["INDICIO_GASTO"].mensaje


# ---------------------------------------------------------------------------
# Por la API, con el archivo de ejemplo
# ---------------------------------------------------------------------------


def test_el_cruce_reconstruye_los_cinco_topes_del_archivo_de_ejemplo(client):
    token = _crear_contador_y_token(client, "cruce-a@example.com")
    cid, pid = _crear_contribuyente_con_periodo(client, token)
    _subir_fixture(client, token, cid, pid)

    cruce = client.get(
        f"/contribuyentes/{cid}/periodos-fiscales/{pid}/cruce-dian",
        headers=_headers(token),
    )
    assert cruce.status_code == 200
    cuerpo = cruce.json()
    assert [t["numero"] for t in cuerpo["topes"]] == [1, 2, 3, 4, 5]
    assert all(t["cuadra"] for t in cuerpo["topes"])
    # Sin nada registrado todavía, el patrimonio y los ingresos quedan cortos.
    severidades = {c["clave"]: c["severidad"] for c in cuerpo["comparaciones"]}
    assert severidades["PATRIMONIO"] == "ALTA"
    assert severidades["INGRESOS"] == "ALTA"
    assert severidades["RETENCIONES"] == "OPORTUNIDAD"
    assert cuerpo["resumen"]["ALTA"] >= 2


def test_el_cruce_sin_exogena_responde_404_y_es_del_contador_dueno(client):
    token = _crear_contador_y_token(client, "cruce-b@example.com")
    cid, pid = _crear_contribuyente_con_periodo(client, token)
    url = f"/contribuyentes/{cid}/periodos-fiscales/{pid}/cruce-dian"
    assert client.get(url, headers=_headers(token)).status_code == 404

    _subir_fixture(client, token, cid, pid)
    otro = _crear_contador_y_token(client, "cruce-c@example.com")
    assert client.get(url, headers=_headers(otro)).status_code == 404


def test_declarar_menos_que_el_ano_pasado_no_es_lo_mismo_que_omitir_un_bien():
    """El Tope 2 es el mayor entre lo reportado por terceros y lo declarado el
    año anterior. Quedar por debajo de lo primero es una omisión; por debajo de
    lo segundo, algo que hay que poder explicar.
    """
    def cruce_con(declarado):
        return _por_clave(comparar(
            [], {2: D("400000000")}, CifrasDeclaradas({29: D(declarado)}, uvt=UVT),
            patrimonio_de_terceros=D("250000000"),
            patrimonio_anio_anterior=D("400000000"),
        ))["PATRIMONIO"]

    omision = cruce_con("200000000")
    assert omision.severidad == ALTA
    assert omision.diferencia == D("-50000000")
    assert "terceros" in omision.mensaje

    baja = cruce_con("300000000")
    assert baja.severidad == MEDIA
    assert baja.diferencia == D("-100000000")
    assert "año anterior" in baja.mensaje or "año\nanterior" in baja.mensaje

    assert cruce_con("400000000").severidad == OK
