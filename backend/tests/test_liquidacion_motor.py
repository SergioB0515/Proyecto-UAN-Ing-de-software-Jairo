"""Pruebas del motor de liquidación.

Se prueban contra la fórmula que trae la norma, recalculada aquí de forma
independiente, no contra el resultado que produjo el propio motor. Si ambos
lados usaran el mismo código la prueba no probaría nada.

No tocan la base de datos a propósito: la aritmética tributaria tiene que poder
verificarse con lápiz y papel, y para eso el motor no debe necesitar Postgres.
"""

from decimal import ROUND_HALF_UP, Decimal as D

import pytest

from modulos.liquidacion.motor import (
    AnioGravableNoSoportadoError,
    ConceptoDepuracion,
    Dividendos,
    GananciasOcasionales,
    InsumosLiquidacion,
    Patrimonio,
    Pensiones,
    RentasDeTrabajo,
    RentasPorSubcedula,
    aplicar_tabla,
    aproximar_al_multiplo_de_mil,
    liquidar,
)
from modulos.parametros.tablas_oficiales import PARAMETROS_POR_ANIO

P2025 = PARAMETROS_POR_ANIO[2025]
UVT = P2025.uvt  # 49.799


def _liquidar(**kwargs):
    insumos = InsumosLiquidacion(anio_gravable=2025, **kwargs)
    return liquidar(insumos, P2025)


# ---------------------------------------------------------------------------
# Tabla del artículo 241
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base_uvt, desde, acumulado, marginal",
    [
        (D("500"), D("0"), D("0"), D("0.00")),
        (D("1500"), D("1090"), D("0"), D("0.19")),
        (D("3000"), D("1700"), D("116"), D("0.28")),
        (D("6000"), D("4100"), D("788"), D("0.33")),
        (D("12000"), D("8670"), D("2296"), D("0.35")),
        (D("25000"), D("18970"), D("5901"), D("0.37")),
        (D("40000"), D("31000"), D("10352"), D("0.39")),
    ],
)
def test_cada_tramo_de_la_tabla_241(base_uvt, desde, acumulado, marginal):
    """Recalcula cada tramo con la fórmula impresa en el Estatuto."""
    base_pesos = base_uvt * UVT
    esperado_uvt = acumulado + (base_uvt - desde) * marginal
    esperado = (esperado_uvt * UVT).quantize(D("0.01"))

    impuesto, formula, _ = aplicar_tabla(base_pesos, P2025.tabla_renta, UVT)

    assert impuesto == esperado
    assert "UVT" in formula


def test_base_en_el_tramo_exento_no_genera_impuesto():
    impuesto, _, _ = aplicar_tabla(D("1089") * UVT, P2025.tabla_renta, UVT)
    assert impuesto == D("0")


def test_el_limite_inferior_de_un_tramo_no_entra_en_ese_tramo():
    """La tabla dice «superior a», no «desde»: 1.090 UVT exactos siguen exentos."""
    impuesto, _, _ = aplicar_tabla(D("1090") * UVT, P2025.tabla_renta, UVT)
    assert impuesto == D("0")


# ---------------------------------------------------------------------------
# Límite del artículo 336 numeral 3
# ---------------------------------------------------------------------------


def test_el_limite_del_40_por_ciento_recorta_y_lo_reporta():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")),
        conceptos_depuracion=[
            ConceptoDepuracion("Aportes voluntarios", D("60000000"), True, "Art. 126-1 ET")
        ],
    )
    # 40 % × 100.000.000 = 40.000.000, menor que el tope de 1.340 UVT.
    assert liq.valor("CG-EXENTAS-LIMITADAS") == D("40000000.00")
    assert any("40 %" in d for d in liq.diagnosticos)
    assert any("no se traslada" in d for d in liq.diagnosticos)


def test_el_tope_de_1340_uvt_manda_cuando_es_menor_que_el_40_por_ciento():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("400000000")),
        conceptos_depuracion=[
            ConceptoDepuracion("Aportes voluntarios", D("100000000"), True, "Art. 126-1 ET")
        ],
    )
    tope = D("1340") * UVT  # 66.730.660
    assert liq.valor("CG-EXENTAS-LIMITADAS") == tope.quantize(D("0.01"))
    assert any("1340 UVT" in d for d in liq.diagnosticos)


def test_no_recorta_ni_avisa_cuando_lo_solicitado_cabe_en_el_limite():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")),
        conceptos_depuracion=[
            ConceptoDepuracion("Intereses de vivienda", D("5000000"), True, "Art. 119 ET")
        ],
    )
    # Solicitado: 5.000.000 + exención del 25 % sobre 95.000.000 = 23.750.000.
    assert liq.valor("CG-EXENTAS-LIMITADAS") == D("28750000.00")
    assert liq.diagnosticos == []


def test_la_base_del_40_por_ciento_son_los_ingresos_menos_incrngo_no_los_netos_de_costos():
    """El 40 % se calcula antes de restar costos y gastos (art. 336 num. 3).

    Tomarlo después de los costos daría un límite más bajo y un impuesto más
    alto: es el error que esta prueba vigila.
    """
    liq = _liquidar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("200000000"), costos_y_gastos=D("150000000")
        ),
        conceptos_depuracion=[
            ConceptoDepuracion("Deducción X", D("50000000"), True, "")
        ],
    )
    assert liq.valor("CG-BASE-LIMITE") == D("200000000")
    assert liq.valor("CG-EXENTAS-LIMITADAS") == D("50000000.00")  # cabe en el 40 %


# ---------------------------------------------------------------------------
# Renta exenta del 25 % y la exclusión del artículo 336 numeral 4
# ---------------------------------------------------------------------------


def test_la_exencion_del_25_por_ciento_se_topa_en_790_uvt():
    liq = _liquidar(trabajo=RentasDeTrabajo(ingresos_brutos=D("300000000")))
    tope = (D("790") * UVT).quantize(D("0.01"))  # 39.341.210
    assert liq.valor("CG-EXENTA-25") == tope


def test_la_exencion_del_25_se_calcula_sobre_el_subtotal_depurado():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(
            ingresos_brutos=D("100000000"),
            aportes_obligatorios_salud=D("4000000"),
            aportes_obligatorios_pension=D("4000000"),
        ),
        conceptos_depuracion=[
            ConceptoDepuracion("Intereses de vivienda", D("12000000"), True, "Art. 119 ET")
        ],
    )
    # 25 % × (100.000.000 − 8.000.000 − 12.000.000) = 20.000.000
    assert liq.valor("CG-EXENTA-25") == D("20000000.00")


def test_optar_por_costos_en_honorarios_hace_perder_la_exencion_del_25():
    sin_costos = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_sin_vinculo_laboral=D("120000000"))
    )
    con_costos = _liquidar(
        trabajo=RentasDeTrabajo(
            ingresos_sin_vinculo_laboral=D("120000000"),
            costos_y_gastos_sin_vinculo_laboral=D("30000000"),
            opta_por_costos_y_gastos=True,
        )
    )
    assert sin_costos.valor("CG-EXENTA-25") == D("30000000.00")  # 25 % de 120.000.000
    assert con_costos.valor("CG-EXENTA-25") == D("0")
    assert con_costos.valor("CG-COSTOS") == D("30000000")


# ---------------------------------------------------------------------------
# Deducciones fuera del límite general
# ---------------------------------------------------------------------------


def test_dependientes_y_el_1_por_ciento_de_compras_no_entran_en_el_limite():
    """Son adicionales al 40 %: si entraran, el impuesto saldría más alto."""
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")),
        conceptos_depuracion=[
            ConceptoDepuracion("Aportes voluntarios", D("60000000"), True, "")
        ],
        numero_dependientes=3,
        compras_con_factura_electronica=D("50000000"),
    )
    assert liq.valor("DED-DEPENDIENTES") == (D("3") * D("72") * UVT).quantize(D("0.01"))
    assert liq.valor("DED-COMPRAS-1PCT") == D("500000.00")
    # El límite recortó a 40.000.000, pero estas dos se restan por encima.
    esperada = (
        D("100000000") - D("40000000")
        - (D("3") * D("72") * UVT).quantize(D("0.01"))
        - D("500000.00")
    )
    assert liq.valor("CG-RENTA-LIQUIDA") == esperada


def test_los_dependientes_se_reconocen_hasta_cuatro():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")), numero_dependientes=7
    )
    assert liq.valor("DED-DEPENDIENTES") == (D("4") * D("72") * UVT).quantize(D("0.01"))
    renglon = next(r for r in liq.renglones if r.codigo == "DED-DEPENDIENTES")
    assert "máximo 4" in renglon.formula


def test_la_deduccion_del_1_por_ciento_se_topa_en_240_uvt():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")),
        compras_con_factura_electronica=D("5000000000"),
    )
    assert liq.valor("DED-COMPRAS-1PCT") == (D("240") * UVT).quantize(D("0.01"))


# ---------------------------------------------------------------------------
# Pensiones
# ---------------------------------------------------------------------------


def test_las_pensiones_son_exentas_hasta_1000_uvt_mensuales():
    liq = _liquidar(pensiones=Pensiones(ingresos_brutos=D("300000000"), meses_causados=12))
    tope = D("1000") * D("12") * UVT  # 597.588.000
    assert liq.valor("PEN-EXENTA") == D("300000000")  # el ingreso completo cabe
    assert liq.valor("PEN-RENTA-LIQUIDA") == D("0")
    assert tope > D("300000000")


def test_la_pension_que_supera_el_tope_mensual_tributa_por_el_exceso():
    liq = _liquidar(pensiones=Pensiones(ingresos_brutos=D("700000000"), meses_causados=12))
    tope = D("1000") * D("12") * UVT
    assert liq.valor("PEN-EXENTA") == tope
    assert liq.valor("PEN-RENTA-LIQUIDA") == D("700000000") - tope


# ---------------------------------------------------------------------------
# Ganancias ocasionales
# ---------------------------------------------------------------------------


def test_la_ganancia_ocasional_tributa_al_15_por_ciento_sobre_la_base_neta():
    liq = _liquidar(
        ganancias_ocasionales=GananciasOcasionales(
            ingresos=D("500000000"), costos=D("200000000"), ganancia_exenta=D("100000000")
        )
    )
    assert liq.valor("GO-BASE") == D("200000000")
    assert liq.valor("GO-IMPUESTO") == D("30000000.00")  # 15 %


def test_loterias_y_rifas_tributan_a_su_tarifa_propia():
    liq = _liquidar(
        ganancias_ocasionales=GananciasOcasionales(loterias_rifas_apuestas=D("50000000"))
    )
    assert liq.valor("GO-IMPUESTO") == D("10000000.00")  # 20 %


def test_la_ganancia_ocasional_no_entra_en_la_base_de_la_tabla_241():
    """Tiene tarifa propia: sumarla a la base progresiva la gravaría dos veces."""
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")),
        ganancias_ocasionales=GananciasOcasionales(ingresos=D("900000000")),
    )
    assert liq.valor("BASE-GRAVABLE") == liq.valor("CG-RENTA-LIQUIDA")


# ---------------------------------------------------------------------------
# Dividendos y descuentos
# ---------------------------------------------------------------------------


def test_los_dividendos_generan_el_descuento_del_254_1_sobre_el_exceso_de_1090_uvt():
    dividendos = D("300000000")
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000")),
        dividendos=Dividendos(no_gravados=dividendos),
    )
    umbral = D("1090") * UVT  # 54.280.910
    esperado = ((dividendos - umbral) * D("0.19")).quantize(D("0.01"))
    assert liq.valor("DESC-DIVIDENDOS") == esperado
    assert liq.valor("DIV-RENTA-LIQUIDA") == dividendos


def test_dividendos_por_debajo_del_umbral_no_generan_descuento():
    liq = _liquidar(dividendos=Dividendos(no_gravados=D("40000000")))
    assert liq.valor("DESC-DIVIDENDOS") == D("0")


def test_los_descuentos_no_pueden_exceder_el_impuesto_a_cargo():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("80000000")),
        otros_descuentos_tributarios=D("999000000"),
    )
    assert liq.valor("TOTAL-DESCUENTOS") == liq.valor("TOTAL-A-CARGO")
    assert liq.valor("IMP-NETO") == D("0")
    assert any("no pueden exceder" in d for d in liq.diagnosticos)


# ---------------------------------------------------------------------------
# Saldo
# ---------------------------------------------------------------------------


def test_cuando_las_retenciones_superan_el_impuesto_queda_saldo_a_favor():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("90000000")),
        retenciones_en_la_fuente=D("30000000"),
    )
    assert liq.valor("SALDO-A-PAGAR") == D("0")
    assert liq.valor("SALDO-A-FAVOR") > D("0")
    assert liq.valor("SALDO-A-FAVOR") == (
        D("30000000") - liq.valor("IMP-NETO") - liq.valor("ANTICIPO-SIGUIENTE")
    )


def test_el_saldo_a_favor_del_ano_anterior_se_imputa():
    sin_saldo = _liquidar(trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000")))
    con_saldo = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000")),
        saldo_a_favor_anio_anterior=D("5000000"),
    )
    assert con_saldo.valor("SALDO-A-PAGAR") == sin_saldo.valor("SALDO-A-PAGAR") - D("5000000")


def test_el_anticipo_usa_el_porcentaje_del_ano_de_declaracion():
    comun = {"trabajo": RentasDeTrabajo(ingresos_brutos=D("250000000"))}
    primero = _liquidar(anios_declarando=1, **comun)
    segundo = _liquidar(anios_declarando=2, **comun)
    tercero = _liquidar(anios_declarando=3, **comun)
    neto = tercero.valor("IMP-NETO")

    # ROUND_HALF_UP explícito: el redondeo por defecto de Decimal.quantize es
    # ROUND_HALF_EVEN (bancario), que a 0,005 redondea al par y difiere en un
    # centavo. En moneda se usa medio arriba, y el motor lo hace así.
    def esperado(porcentaje):
        return (neto * porcentaje).quantize(D("0.01"), rounding=ROUND_HALF_UP)

    assert primero.valor("ANTICIPO-SIGUIENTE") == esperado(D("0.25"))
    assert segundo.valor("ANTICIPO-SIGUIENTE") == esperado(D("0.50"))
    assert tercero.valor("ANTICIPO-SIGUIENTE") == esperado(D("0.75"))


# ---------------------------------------------------------------------------
# Patrimonio, redondeo y precisión
# ---------------------------------------------------------------------------


def test_el_patrimonio_liquido_es_el_bruto_menos_las_deudas():
    liq = _liquidar(
        patrimonio=Patrimonio(patrimonio_bruto=D("500000000"), deudas=D("120000000"))
    )
    assert liq.valor("PAT-LIQUIDO") == D("380000000")


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (D("1499"), D("1000")),
        (D("1500"), D("2000")),
        (D("1501"), D("2000")),
        (D("8008464.32"), D("8008000")),
        (D("0"), D("0")),
    ],
)
def test_los_valores_declarables_se_aproximan_al_multiplo_de_mil(valor, esperado):
    """Art. 577 ET. La aproximación es solo del valor que se transcribe."""
    assert aproximar_al_multiplo_de_mil(valor) == esperado


def test_el_valor_calculado_conserva_los_centavos_y_el_declarable_no():
    liq = _liquidar(trabajo=RentasDeTrabajo(ingresos_brutos=D("123456789")))
    renglon = next(r for r in liq.renglones if r.codigo == "IMP-RENTA")
    assert renglon.valor != renglon.valor_declarable
    assert renglon.valor_declarable % D("1000") == D("0")


def test_la_suma_de_decimales_no_arrastra_error_de_float():
    """Con float, 0.1 × 3 no da 0.3. Con Decimal sí, y los totales cuadran."""
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000.10")),
        capital=RentasPorSubcedula(ingresos_brutos=D("0.10")),
        no_laborales=RentasPorSubcedula(ingresos_brutos=D("0.10")),
    )
    assert liq.valor("CG-INGRESOS") == D("100000000.30")


# ---------------------------------------------------------------------------
# Parámetros y años
# ---------------------------------------------------------------------------


def test_un_ano_sin_parametros_falla_en_vez_de_liquidar_con_otros():
    insumos = InsumosLiquidacion(anio_gravable=2019)
    with pytest.raises(AnioGravableNoSoportadoError):
        liquidar(insumos, P2025)


@pytest.mark.parametrize("anio", sorted(PARAMETROS_POR_ANIO))
def test_todos_los_anos_cargados_liquidan_y_citan_su_fuente(anio):
    parametros = PARAMETROS_POR_ANIO[anio]
    insumos = InsumosLiquidacion(
        anio_gravable=anio, trabajo=RentasDeTrabajo(ingresos_brutos=D("150000000"))
    )
    liq = liquidar(insumos, parametros)
    assert liq.valor("IMP-RENTA") > D("0")
    assert all(r.fuente_legal or r.formula for r in liq.renglones)


def test_la_uvt_de_cada_ano_cambia_el_impuesto():
    """Mismo ingreso nominal, años distintos: el reajuste de la UVT baja el impuesto."""
    impuestos = {}
    for anio, parametros in sorted(PARAMETROS_POR_ANIO.items()):
        insumos = InsumosLiquidacion(
            anio_gravable=anio, trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000"))
        )
        impuestos[anio] = liquidar(insumos, parametros).valor("IMP-RENTA")
    anios = sorted(impuestos)
    assert all(impuestos[a] > impuestos[b] for a, b in zip(anios, anios[1:]))


def test_cada_renglon_sale_con_formula_o_fuente_legal():
    """Trazabilidad: un renglón sin rastro no es auditable y no debe existir."""
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("150000000")),
        pensiones=Pensiones(ingresos_brutos=D("20000000")),
        dividendos=Dividendos(no_gravados=D("80000000")),
        ganancias_ocasionales=GananciasOcasionales(ingresos=D("60000000")),
        numero_dependientes=1,
        compras_con_factura_electronica=D("10000000"),
        conceptos_depuracion=[ConceptoDepuracion("Medicina prepagada", D("4000000"), True, "Art. 387 ET")],
    )
    sin_rastro = [r.codigo for r in liq.renglones if not r.formula and not r.fuente_legal]
    assert sin_rastro == []
