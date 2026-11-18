"""Cálculos de la gestión de la declaración: cada prueba cita la norma que fija."""

from datetime import date
from decimal import Decimal as D

from modulos.gestion.calculos import (
    RegistroParaDocumentos,
    calcular_beneficio_auditoria,
    calcular_correccion,
    calcular_firmeza,
    calcular_intereses,
    comparar_con_anterior,
    meses_o_fraccion,
    sugerir_documentos,
    sumar_meses,
)

UVT_2024 = D("47065")
UVT_2025 = D("49799")
VENCE = date(2026, 8, 20)


# Firmeza (art. 714)


def test_firmeza_general_es_tres_anos_desde_el_vencimiento():
    f = calcular_firmeza(VENCE, date(2026, 8, 1))
    assert f.fecha == date(2029, 8, 20)
    assert "vencimiento" in f.regla


def test_presentada_tarde_cuenta_desde_la_presentacion():
    f = calcular_firmeza(VENCE, date(2026, 10, 3))
    assert f.fecha == date(2029, 10, 3)


def test_con_perdidas_son_cinco_anos():
    assert calcular_firmeza(VENCE, date(2026, 8, 1),
                            liquida_o_compensa_perdidas=True).fecha == date(2031, 8, 20)


def test_saldo_a_favor_cuenta_desde_la_solicitud_de_devolucion():
    f = calcular_firmeza(VENCE, date(2026, 8, 1), tiene_saldo_a_favor=True,
                         solicitud_devolucion=date(2026, 11, 15))
    assert f.fecha == date(2029, 11, 15)


def test_beneficio_de_auditoria_cuenta_desde_la_presentacion():
    f = calcular_firmeza(VENCE, date(2026, 8, 1), meses_beneficio_auditoria=6)
    assert f.fecha == date(2027, 2, 1)
    assert "689-3" in f.fuente


def test_sin_presentar_no_hay_fecha():
    assert calcular_firmeza(VENCE, None).fecha is None


def test_sumar_meses_respeta_el_fin_de_mes():
    assert sumar_meses(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert sumar_meses(date(2028, 2, 29), 12) == date(2029, 2, 28)


# Beneficio de auditoría (art. 689-3, Ley 2294 de 2023 art. 69)


def test_incremento_de_35_por_ciento_da_seis_meses():
    b = calcular_beneficio_auditoria(2025, D("13500000"), D("10000000"), UVT_2024,
                                     True, True)
    assert b.meses == 6
    assert b.incremento == D("0.35")


def test_incremento_de_25_por_ciento_da_doce_meses():
    b = calcular_beneficio_auditoria(2025, D("12600000"), D("10000000"), UVT_2024,
                                     True, True)
    assert b.meses == 12


def test_dice_cuanto_impuesto_haria_falta_cuando_no_alcanza():
    b = calcular_beneficio_auditoria(2025, D("11000000"), D("10000000"), UVT_2024,
                                     True, True)
    assert b.meses is None
    assert b.impuesto_para_12_meses == D("12500000")
    assert b.impuesto_para_6_meses == D("13500000")
    assert "12.500.000" in b.conclusion


def test_el_impuesto_anterior_debe_ser_de_al_menos_71_uvt_del_ano_anterior():
    # 71 × 47.065 = 3.341.615: un peso menos y no aplica, aunque se duplique.
    b = calcular_beneficio_auditoria(2025, D("9000000"), D("3341614"), UVT_2024,
                                     True, True)
    assert b.meses is None
    assert "71 uvt" in b.conclusion.lower()
    assert calcular_beneficio_auditoria(2025, D("9000000"), D("3341615"), UVT_2024,
                                        True, True).meses == 6


def test_presentar_tarde_hace_perder_el_beneficio():
    b = calcular_beneficio_auditoria(2025, D("20000000"), D("10000000"), UVT_2024,
                                     False, True)
    assert b.meses is None


def test_sin_pago_registrado_alcanza_pero_queda_condicionado():
    b = calcular_beneficio_auditoria(2025, D("20000000"), D("10000000"), UVT_2024,
                                     True, None)
    assert b.meses == 6
    assert "pendientes" in b.conclusion


def test_fuera_de_los_anos_prorrogados_no_hay_beneficio():
    b = calcular_beneficio_auditoria(2027, D("20000000"), D("10000000"), UVT_2025,
                                     True, True)
    assert not b.vigente and b.meses is None


# Corrección (arts. 588, 589, 644)


def test_correccion_que_aumenta_lleva_el_10_por_ciento_del_mayor_valor():
    # Mayor valor de 10 M: el 10 % (1 M) supera la mínima de 10 UVT (497.990).
    c = calcular_correccion(D("5000000"), D("0"), D("15000000"), D("0"),
                            VENCE, date(2026, 8, 10), date(2026, 12, 1), UVT_2025)
    assert c.tipo == "AUMENTA"
    assert c.mayor_valor == D("10000000")
    assert c.sancion == D("1000000")
    assert c.plazo == date(2029, 8, 20)


def test_menor_saldo_a_favor_tambien_es_mayor_valor():
    c = calcular_correccion(D("0"), D("4000000"), D("0"), D("1000000"),
                            VENCE, date(2026, 8, 10), date(2026, 12, 1), UVT_2025)
    assert c.mayor_valor == D("3000000")


def test_despues_del_emplazamiento_es_el_20_por_ciento():
    c = calcular_correccion(D("5000000"), D("0"), D("15000000"), D("0"), VENCE,
                            date(2026, 8, 10), date(2027, 3, 1), UVT_2025,
                            despues_de_emplazamiento=True)
    assert c.sancion == D("2000000")


def test_si_la_inicial_fue_extemporanea_suma_5_por_ciento_por_mes():
    # Inicial presentada el 25 de sept. (vencía el 20 de agosto): 2 meses.
    c = calcular_correccion(D("5000000"), D("0"), D("15000000"), D("0"), VENCE,
                            date(2026, 9, 25), date(2026, 12, 1), UVT_2025)
    assert c.sancion == D("2000000")    # 10 % + 2 × 5 % = 20 % de 10 M


def test_la_sancion_por_correccion_tiene_minimo_de_10_uvt():
    c = calcular_correccion(D("5000000"), D("0"), D("5100000"), D("0"), VENCE,
                            date(2026, 8, 10), date(2026, 12, 1), UVT_2025)
    assert c.sancion == D("497990")


def test_la_reduccion_del_640_se_aplica_antes_del_minimo():
    c = calcular_correccion(D("5000000"), D("0"), D("25000000"), D("0"), VENCE,
                            date(2026, 8, 10), date(2026, 12, 1), UVT_2025,
                            reduccion="AL_50")
    assert c.sancion == D("1000000")


def test_correccion_que_disminuye_no_lleva_sancion_y_tiene_un_ano():
    c = calcular_correccion(D("8000000"), D("0"), D("5000000"), D("0"),
                            VENCE, date(2026, 8, 10), date(2027, 9, 1), UVT_2025)
    assert c.tipo == "DISMINUYE" and c.sancion == D("0")
    assert c.plazo == date(2027, 8, 20)
    assert c.vencida is True


def test_meses_o_fraccion_cuenta_un_dia_como_un_mes():
    assert meses_o_fraccion(date(2026, 8, 20), date(2026, 8, 21)) == 1
    assert meses_o_fraccion(date(2026, 8, 20), date(2026, 9, 20)) == 1
    assert meses_o_fraccion(date(2026, 8, 20), date(2026, 9, 21)) == 2


# Intereses de mora (arts. 634 y 635)

TASAS = {(2026, 8): D("0.2766"), (2026, 9): D("0.2724")}


def test_intereses_por_tramos_mensuales_con_la_tasa_de_cada_mes():
    # Vence 20 de agosto, paga 30 de septiembre: 11 días de agosto y 30 de sept.
    r = calcular_intereses(D("10000000"), VENCE, date(2026, 9, 30), TASAS)
    assert r.dias == 41
    assert [t.dias for t in r.tramos] == [11, 30]
    agosto = D("10000000") * D("0.2766") / 365 * 11
    septiembre = D("10000000") * D("0.2724") / 365 * 30
    assert r.valor == (agosto + septiembre).quantize(D("1"))
    assert r.valor == D("307249")   # 83.358,90 + 223.890,41


def test_sin_la_tasa_de_un_mes_no_la_inventa():
    r = calcular_intereses(D("10000000"), VENCE, date(2026, 11, 5), TASAS)
    assert r.meses_sin_tasa == [(2026, 10), (2026, 11)]
    assert len(r.tramos) == 2


def test_pagar_a_tiempo_no_genera_intereses():
    assert calcular_intereses(D("10000000"), VENCE, VENCE, TASAS).valor == D("0")


# Comparativo


def test_marca_las_variaciones_grandes_y_no_las_pequenas():
    comp = comparar_con_anterior(
        {29: D("300000000"), 32: D("100000000"), 126: D("5000000")},
        {29: D("200000000"), 32: D("95000000"), 126: D("5000000")},
        umbral_minimo=D("1000000"),
    )
    filas = {f.casilla: f for f in comp.filas}
    assert filas[29].revisar is True
    assert filas[32].revisar is False
    assert filas[126].diferencia == D("0")


def test_el_anticipo_y_el_saldo_a_favor_deben_venir_del_ano_anterior():
    comp = comparar_con_anterior(
        {130: D("2000000"), 131: D("0")},
        {133: D("2500000"), 137: D("800000")},
        umbral_minimo=D("1000000"),
    )
    anticipo, saldo = comp.coherencias
    assert anticipo.cuadra is False and anticipo.esperado == D("2500000")
    assert saldo.cuadra is False and saldo.esperado == D("800000")


# Documentos


def _reg(nit, nombre, detalle, concepto=None, info=None, **kw):
    return RegistroParaDocumentos(nit, nombre, detalle, concepto, info, **kw)


def test_un_certificado_por_tercero_y_tipo():
    docs = sugerir_documentos([
        _reg("860002964", "BANCO DE BOGOTA", "Saldo de cuentas de ahorro (Concepto: 1110)", "1110"),
        _reg("860002964", "BANCO DE BOGOTA", "Rendimientos financieros (Concepto: 1301)", "1301"),
        _reg("860007336", "FUNDACION", "Pagos por salarios (Concepto: 5001)", "5001"),
        _reg("860007336", "FUNDACION", "Retención en la fuente practicada por salarios"),
    ], tiene_declaracion_anterior=True)
    claves = sorted(d.clave for d in docs)
    assert claves == ["BANCARIO:860002964", "CERT_220:860007336"]
    banco = next(d for d in docs if d.clave.startswith("BANCARIO"))
    assert "Rendimientos" in banco.motivo and "Saldo" in banco.motivo


def test_cada_inmueble_tiene_su_predial():
    docs = sugerir_documentos([
        _reg("899999061", "HACIENDA", "Valor avalúo catastral (Concepto: 1476)", "1476",
             info="Matrícula: 50N-20384756 | Participación: 100.00"),
        _reg("899999061", "HACIENDA", "Valor avalúo catastral (Concepto: 1476)", "1476",
             info="Matrícula: 50S-40117823 | Participación: 50.00"),
    ], tiene_declaracion_anterior=True)
    assert sorted(d.clave for d in docs) == ["PREDIAL:50N-20384756", "PREDIAL:50S-40117823"]


def test_lo_que_reporta_la_dian_o_el_propio_contribuyente_no_se_pide():
    docs = sugerir_documentos([
        _reg("800197268", "DIAN", "Suma valor total facturas", es_dian=True),
        _reg("1000000000", "YO", "Total saldo a favor", es_auto_reportado=True),
    ], tiene_declaracion_anterior=True)
    assert docs == []


def test_las_deducciones_y_la_declaracion_anterior_generan_solicitud():
    docs = sugerir_documentos([], ["INTERESES_VIVIENDA", "MEDICINA_PREPAGADA"],
                              numero_dependientes=2)
    claves = {d.clave for d in docs}
    assert {"DEDUCCION:INTERESES_VIVIENDA", "DEDUCCION:MEDICINA_PREPAGADA",
            "DEPENDIENTES", "DECLARACION_ANTERIOR"} == claves


def test_una_casilla_no_copiada_de_la_declaracion_anterior_no_se_marca():
    comp = comparar_con_anterior({111: D("80000000")}, {29: D("1")},
                                 umbral_minimo=D("1000000"), anterior_incompleto=True)
    fila = next(f for f in comp.filas if f.casilla == 111)
    assert fila.revisar is False and fila.diferencia is None
    # Si la anterior se presentó desde la app, una casilla ausente sí es cero.
    comp = comparar_con_anterior({111: D("80000000")}, {29: D("1")},
                                 umbral_minimo=D("1000000"))
    assert next(f for f in comp.filas if f.casilla == 111).revisar is True


def test_la_conclusion_dice_que_condicion_falla_y_con_que_cifras():
    b = calcular_beneficio_auditoria(2025, D("9000000"), D("1450000"), UVT_2024, True, True)
    assert "71 UVT" in b.conclusion
    assert "$1.450.000" in b.conclusion and "$3.341.615" in b.conclusion


def test_la_tarjeta_y_la_cuenta_del_mismo_banco_son_un_solo_certificado():
    docs = sugerir_documentos([
        _reg("890903938", "BANCOLOMBIA", "Total consumos con tarjeta (Concepto: 1023)", "1023"),
        _reg("890903938", "BANCOLOMBIA", "Valor total de los movimientos en cuentas"),
    ], tiene_declaracion_anterior=True)
    assert [d.clave for d in docs] == ["BANCARIO:890903938"]
