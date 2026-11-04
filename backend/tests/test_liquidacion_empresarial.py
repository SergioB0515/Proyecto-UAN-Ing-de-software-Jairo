"""Pruebas de los cálculos empresariales: depreciación, bancarización,
compensación de pérdidas, comparación patrimonial y anticipo.

Como en `test_liquidacion_motor.py`, los valores esperados se recalculan aquí
con la fórmula de la norma, no se copian de la salida del motor.
"""

from decimal import ROUND_HALF_UP, Decimal as D

import pytest

from modulos.liquidacion.calculos_empresariales import (
    ActivoDepreciable,
    InsumosBancarizacion,
    InsumosComparacionPatrimonial,
    PagoIndividual,
    PerdidaCompensable,
    calcular_bancarizacion,
    calcular_comparacion_patrimonial,
    calcular_compensacion_perdidas,
    calcular_depreciacion,
)
from modulos.liquidacion.motor import (
    ConceptoDepuracion,
    GananciasOcasionales,
    InsumosLiquidacion,
    Patrimonio,
    RentasDeTrabajo,
    RentasPorSubcedula,
    liquidar,
)
from modulos.parametros.tablas_oficiales import PARAMETROS_POR_ANIO

P = PARAMETROS_POR_ANIO[2025]
UVT = P.uvt


def _liquidar(**kwargs):
    return liquidar(InsumosLiquidacion(anio_gravable=2025, **kwargs), P)


# ---------------------------------------------------------------------------
# Depreciación (arts. 128 a 131 y 137 ET)
# ---------------------------------------------------------------------------


def test_la_depreciacion_se_calcula_por_linea_recta_sobre_la_base_depreciable():
    activo = ActivoDepreciable(
        "Bodega", D("500000000"), "CONSTRUCCIONES_Y_EDIFICACIONES", 50, D("50000000")
    )
    resultado = calcular_depreciacion([activo], P)
    # Base 450.000.000 ÷ 50 años = 9.000.000; el tope del 2,22 % da 9.990.000.
    assert resultado.total == D("9000000.00")
    assert resultado.diagnosticos == []


def test_la_tasa_del_articulo_137_recorta_una_vida_util_demasiado_corta():
    activo = ActivoDepreciable(
        "Camioneta", D("120000000"), "FLOTA_Y_EQUIPO_DE_TRANSPORTE_TERRESTRE", 5,
        D("20000000"),
    )
    resultado = calcular_depreciacion([activo], P)
    base = D("100000000")
    assert resultado.total == (base * D("0.10")).quantize(D("0.01"))  # 10 %, no 20 %
    assert any("art. 137" in d for d in resultado.diagnosticos)


def test_el_valor_residual_sale_de_la_base_depreciable():
    con_residual = calcular_depreciacion(
        [ActivoDepreciable("Máquina", D("100000000"), "MAQUINARIA_Y_EQUIPOS", 10, D("40000000"))], P
    )
    sin_residual = calcular_depreciacion(
        [ActivoDepreciable("Máquina", D("100000000"), "MAQUINARIA_Y_EQUIPOS", 10)], P
    )
    assert con_residual.total == D("6000000.00")
    assert sin_residual.total == D("10000000.00")


def test_un_activo_comprado_a_mitad_de_ano_se_deprecia_proporcionalmente():
    resultado = calcular_depreciacion(
        [ActivoDepreciable("Portátil", D("6000000"), "EQUIPO_DE_COMPUTACION", 5,
                           meses_en_el_periodo=6)], P
    )
    # 6.000.000 ÷ 5 = 1.200.000 al año; seis meses = 600.000. Tope 20 % = 600.000.
    assert resultado.total == D("600000.00")


def test_un_activo_ya_depreciado_por_completo_no_genera_mas_deduccion():
    resultado = calcular_depreciacion(
        [ActivoDepreciable("Mostrador", D("10000000"), "MUEBLES_Y_ENSERES", 10,
                           depreciacion_acumulada=D("10000000"))], P
    )
    assert resultado.total == D("0")
    assert any("ya está depreciado" in d for d in resultado.diagnosticos)


def test_la_depreciacion_nunca_excede_el_saldo_pendiente():
    resultado = calcular_depreciacion(
        [ActivoDepreciable("Equipo", D("10000000"), "MAQUINARIA_Y_EQUIPOS", 10,
                           depreciacion_acumulada=D("9700000"))], P
    )
    assert resultado.total == D("300000.00")


def test_una_categoria_fuera_de_la_tabla_se_excluye_en_vez_de_adivinar_la_tasa():
    resultado = calcular_depreciacion(
        [ActivoDepreciable("Algo raro", D("10000000"), "CATEGORIA_INVENTADA", 10)], P
    )
    assert resultado.total == D("0")
    assert any("no está en la tabla del art. 137" in d for d in resultado.diagnosticos)


def test_la_depreciacion_baja_la_renta_liquida_de_la_subcedula_elegida():
    sin = _liquidar(no_laborales=RentasPorSubcedula(ingresos_brutos=D("200000000")))
    con = _liquidar(
        no_laborales=RentasPorSubcedula(ingresos_brutos=D("200000000")),
        activos_depreciables=[
            ActivoDepreciable("Máquina", D("100000000"), "MAQUINARIA_Y_EQUIPOS", 10)
        ],
    )
    assert con.valor("DEP-TOTAL") == D("10000000.00")
    assert con.valor("CG-RENTA-LIQUIDA") == sin.valor("CG-RENTA-LIQUIDA") - D("10000000")


# ---------------------------------------------------------------------------
# Bancarización (art. 771-5 ET)
# ---------------------------------------------------------------------------


def test_el_efectivo_dentro_de_todos_los_limites_se_acepta_completo():
    resultado = calcular_bancarizacion(
        InsumosBancarizacion(total_pagos_del_anio=D("500000000"), pagos_en_efectivo=D("50000000")),
        costos_y_deducciones_totales=D("400000000"),
        parametros=P,
    )
    # 40 % de 500M = 200M; 35 % de 400M = 140M; 40.000 UVT ≈ 1.992M. Manda el efectivo.
    assert resultado.efectivo_aceptado == D("50000000.00")
    assert resultado.efectivo_rechazado == D("0.00")


def test_manda_el_40_por_ciento_de_los_pagos_cuando_es_la_cifra_menor():
    resultado = calcular_bancarizacion(
        InsumosBancarizacion(total_pagos_del_anio=D("100000000"), pagos_en_efectivo=D("80000000")),
        costos_y_deducciones_totales=D("900000000"),
        parametros=P,
    )
    # 40 % de 100M = 40M; 35 % de 900M = 315M; 40.000 UVT ≈ 1.992M.
    assert resultado.efectivo_aceptado == D("40000000.00")
    assert resultado.efectivo_rechazado == D("40000000.00")
    assert any("40% de los pagos totales" in d for d in resultado.diagnosticos)


def test_los_porcentajes_de_las_formulas_no_salen_en_notacion_cientifica():
    """Decimal.normalize() convierte 40,00 en 4E+1 y el contador leería «4E+1 %»."""
    resultado = calcular_bancarizacion(
        InsumosBancarizacion(total_pagos_del_anio=D("100000000"), pagos_en_efectivo=D("80000000")),
        costos_y_deducciones_totales=D("900000000"),
        parametros=P,
    )
    assert "40%" in resultado.formula
    assert "E+" not in resultado.formula


def test_manda_el_35_por_ciento_de_los_costos_cuando_es_la_cifra_menor():
    resultado = calcular_bancarizacion(
        InsumosBancarizacion(total_pagos_del_anio=D("900000000"), pagos_en_efectivo=D("80000000")),
        costos_y_deducciones_totales=D("100000000"),
        parametros=P,
    )
    assert resultado.efectivo_aceptado == D("35000000.00")  # 35 % de 100M
    assert resultado.efectivo_rechazado == D("45000000.00")


def test_manda_el_tope_de_40000_uvt_cuando_es_la_cifra_menor():
    enorme = D("100000000000")
    resultado = calcular_bancarizacion(
        InsumosBancarizacion(total_pagos_del_anio=enorme, pagos_en_efectivo=enorme),
        costos_y_deducciones_totales=enorme,
        parametros=P,
    )
    assert resultado.efectivo_aceptado == (D("40000") * UVT).quantize(D("0.01"))


def test_las_operaciones_individuales_sobre_100_uvt_se_listan_aparte():
    tope = D("100") * UVT  # 4.979.900
    resultado = calcular_bancarizacion(
        InsumosBancarizacion(
            total_pagos_del_anio=D("100000000"),
            pagos_en_efectivo=D("10000000"),
            operaciones_individuales_en_efectivo=[
                PagoIndividual("Compra de mercancía", tope + D("1")),
                PagoIndividual("Papelería", D("200000")),
            ],
        ),
        costos_y_deducciones_totales=D("80000000"),
        parametros=P,
    )
    assert [o.descripcion for o in resultado.operaciones_sobre_el_limite] == [
        "Compra de mercancía"
    ]
    assert any("límite individual" in d for d in resultado.diagnosticos)


def test_el_limite_individual_se_evalua_aunque_no_haya_efectivo_en_el_total():
    """Son dos límites distintos: el par. 2 no depende del par. 1."""
    resultado = calcular_bancarizacion(
        InsumosBancarizacion(
            operaciones_individuales_en_efectivo=[PagoIndividual("Pago grande", D("50000000"))]
        ),
        costos_y_deducciones_totales=D("100000000"),
        parametros=P,
    )
    assert not resultado.aplica
    assert len(resultado.operaciones_sobre_el_limite) == 1


def test_el_efectivo_rechazado_vuelve_a_la_renta_liquida():
    liq = _liquidar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("200000000"), costos_y_gastos=D("100000000")
        ),
        bancarizacion=InsumosBancarizacion(
            total_pagos_del_anio=D("100000000"), pagos_en_efectivo=D("80000000")
        ),
    )
    # Los costos son 100M, así que el 35 % de los costos (35M) es la cota menor,
    # por debajo del 40 % de los pagos (40M): se aceptan 35M y se rechazan 45M.
    assert liq.valor("CG-EFECTIVO-ACEPTADO") == D("35000000.00")
    assert liq.valor("CG-EFECTIVO-RECHAZADO") == D("45000000.00")
    # 200M − 100M de costos + 45M rechazados = 145M
    assert liq.valor("CG-RL-ANTES") == D("145000000.00")


# ---------------------------------------------------------------------------
# Compensación de pérdidas
# ---------------------------------------------------------------------------


def test_la_perdida_se_compensa_contra_la_renta_del_mismo_tipo():
    resultado = calcular_compensacion_perdidas(
        [PerdidaCompensable(2022, "NO_LABORAL", D("30000000"))],
        {"NO_LABORAL": D("50000000"), "CAPITAL": D("20000000")},
        2025,
        P,
    )
    assert resultado.por_tipo["NO_LABORAL"] == D("30000000.00")
    assert resultado.por_tipo["CAPITAL"] == D("0.00")


def test_una_perdida_no_se_compensa_contra_otro_tipo_de_renta():
    """Art. 330: la pérdida de arrendamientos no baja la utilidad del negocio."""
    resultado = calcular_compensacion_perdidas(
        [PerdidaCompensable(2022, "CAPITAL", D("30000000"))],
        {"NO_LABORAL": D("50000000"), "CAPITAL": D("0")},
        2025,
        P,
    )
    assert resultado.por_tipo["NO_LABORAL"] == D("0.00")
    assert resultado.por_tipo["CAPITAL"] == D("0.00")


def test_la_compensacion_no_puede_exceder_la_renta_liquida_del_tipo():
    resultado = calcular_compensacion_perdidas(
        [PerdidaCompensable(2022, "NO_LABORAL", D("80000000"))],
        {"NO_LABORAL": D("30000000")},
        2025,
        P,
    )
    assert resultado.por_tipo["NO_LABORAL"] == D("30000000.00")


def test_una_perdida_de_mas_de_doce_anos_ya_no_se_compensa():
    resultado = calcular_compensacion_perdidas(
        [PerdidaCompensable(2012, "NO_LABORAL", D("30000000"))],
        {"NO_LABORAL": D("50000000")},
        2025,
        P,
    )
    assert resultado.por_tipo["NO_LABORAL"] == D("0.00")
    assert any("12 periodos" in d or "periodos gravables" in d for d in resultado.diagnosticos)


def test_las_perdidas_se_consumen_de_la_mas_antigua_a_la_mas_reciente():
    """Conviene al contribuyente: las que están por caducar se usan primero."""
    resultado = calcular_compensacion_perdidas(
        [
            PerdidaCompensable(2024, "NO_LABORAL", D("40000000")),
            PerdidaCompensable(2015, "NO_LABORAL", D("40000000")),
        ],
        {"NO_LABORAL": D("40000000")},
        2025,
        P,
    )
    assert "2015" in resultado.detalle[0][0]


def test_la_compensacion_baja_la_renta_liquida_de_la_cedula_general():
    liq = _liquidar(
        no_laborales=RentasPorSubcedula(ingresos_brutos=D("100000000")),
        perdidas_compensables=[PerdidaCompensable(2023, "NO_LABORAL", D("25000000"))],
    )
    assert liq.valor("CG-COMPENSACION") == D("25000000.00")
    assert liq.valor("CG-RL-ANTES") == D("75000000.00")


def test_las_rentas_de_trabajo_con_vinculo_no_admiten_compensacion():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")),
        perdidas_compensables=[PerdidaCompensable(2023, "NO_LABORAL", D("25000000"))],
    )
    assert liq.valor("CG-COMPENSACION") == D("0")


# ---------------------------------------------------------------------------
# Comparación patrimonial (arts. 236 a 239 ET)
# ---------------------------------------------------------------------------


def test_la_diferencia_patrimonial_se_calcula_con_la_formula_del_articulo_237():
    resultado = calcular_comparacion_patrimonial(
        InsumosComparacionPatrimonial(
            patrimonio_liquido_anterior=D("200000000"),
            impuestos_pagados_en_el_anio=D("5000000"),
        ),
        patrimonio_liquido_actual=D("300000000"),
        renta_gravable=D("45000000"),
        rentas_exentas=D("15000000"),
        ganancia_ocasional_neta=D("20000000"),
    )
    assert resultado.incremento == D("100000000")
    assert resultado.justificado == D("75000000")
    assert resultado.diferencia == D("25000000")


def test_las_justificaciones_reducen_la_diferencia():
    resultado = calcular_comparacion_patrimonial(
        InsumosComparacionPatrimonial(
            patrimonio_liquido_anterior=D("200000000"), justificaciones=D("25000000")
        ),
        D("300000000"), D("45000000"), D("15000000"), D("20000000"),
    )
    assert resultado.diferencia == D("0")


def test_un_patrimonio_que_no_crece_no_genera_renta_por_comparacion():
    resultado = calcular_comparacion_patrimonial(
        InsumosComparacionPatrimonial(patrimonio_liquido_anterior=D("300000000")),
        D("250000000"), D("45000000"), D("0"), D("0"),
    )
    assert resultado.diferencia == D("0")
    assert "no aumentó" in resultado.formula


def test_la_diferencia_no_entra_a_la_base_sin_que_el_contador_la_acepte():
    """El art. 236 admite prueba en contrario: incorporarla sola inventaría impuesto."""
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("50000000")),
        patrimonio=Patrimonio(patrimonio_bruto=D("500000000")),
        comparacion_patrimonial=InsumosComparacionPatrimonial(
            patrimonio_liquido_anterior=D("100000000")
        ),
    )
    assert liq.valor("COMP-PATRIMONIAL") > D("0")
    assert liq.valor("COMP-PATRIMONIAL-GRAVADA") == D("0")
    assert liq.valor("BASE-GRAVABLE") == liq.valor("CG-RENTA-LIQUIDA")
    assert any("NO se incorporó" in d for d in liq.diagnosticos)


def test_al_aceptarla_la_diferencia_entra_a_la_base_gravable():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("50000000")),
        patrimonio=Patrimonio(patrimonio_bruto=D("500000000")),
        comparacion_patrimonial=InsumosComparacionPatrimonial(
            patrimonio_liquido_anterior=D("100000000"), aceptar_como_renta_gravable=True
        ),
    )
    diferencia = liq.valor("COMP-PATRIMONIAL-GRAVADA")
    assert diferencia > D("0")
    assert liq.valor("BASE-GRAVABLE") == liq.valor("CG-RENTA-LIQUIDA") + diferencia


# ---------------------------------------------------------------------------
# Anticipo (art. 807 ET)
# ---------------------------------------------------------------------------


def _esperado(valor, pct):
    return (valor * pct).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def test_el_metodo_promedio_usa_el_impuesto_neto_de_los_dos_anos():
    comun = {
        "trabajo": RentasDeTrabajo(ingresos_brutos=D("250000000")),
        "impuesto_neto_anio_anterior": D("5000000"),
    }
    directo = _liquidar(metodo_anticipo="DIRECTO", **comun)
    promedio = _liquidar(metodo_anticipo="PROMEDIO", **comun)
    neto = directo.valor("IMP-NETO")
    assert promedio.valor("ANTICIPO-SIGUIENTE") == _esperado(
        (neto + D("5000000")) / D("2"), D("0.75")
    )


def test_el_metodo_menor_escoge_el_que_da_el_anticipo_mas_bajo():
    comun = {
        "trabajo": RentasDeTrabajo(ingresos_brutos=D("250000000")),
        "impuesto_neto_anio_anterior": D("1000000"),
    }
    directo = _liquidar(metodo_anticipo="DIRECTO", **comun)
    menor = _liquidar(metodo_anticipo="MENOR", **comun)
    assert menor.valor("ANTICIPO-SIGUIENTE") < directo.valor("ANTICIPO-SIGUIENTE")
    renglon = next(r for r in menor.renglones if r.codigo == "ANTICIPO-SIGUIENTE")
    assert "Se escogió el menor" in renglon.formula


def test_sin_impuesto_del_ano_anterior_el_promedio_cae_al_metodo_directo():
    """Promediar contra cero daría la mitad del anticipo: sanción asegurada."""
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("250000000")),
        metodo_anticipo="PROMEDIO",
    )
    directo = _liquidar(trabajo=RentasDeTrabajo(ingresos_brutos=D("250000000")))
    assert liq.valor("ANTICIPO-SIGUIENTE") == directo.valor("ANTICIPO-SIGUIENTE")
    assert any("la mitad del anticipo" in d for d in liq.diagnosticos)


def test_avisa_cuando_el_promedio_habria_dado_un_anticipo_menor():
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("250000000")),
        impuesto_neto_anio_anterior=D("1000000"),
        metodo_anticipo="DIRECTO",
    )
    assert any("método del promedio" in d for d in liq.diagnosticos)


# ---------------------------------------------------------------------------
# Costo de ventas
# ---------------------------------------------------------------------------


def test_el_costo_de_ventas_baja_la_renta_liquida_no_laboral():
    """Era el hueco: sin esto, al comerciante se le liquidaba sobre el bruto."""
    sin = _liquidar(no_laborales=RentasPorSubcedula(ingresos_brutos=D("300000000")))
    con = _liquidar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("300000000"), costo_de_ventas=D("180000000")
        )
    )
    assert con.valor("CG-COSTO-VENTAS") == D("180000000")
    assert con.valor("CG-RL-ANTES") == sin.valor("CG-RL-ANTES") - D("180000000")
    assert con.valor("IMP-RENTA") < sin.valor("IMP-RENTA")


def test_el_costo_de_ventas_no_cambia_la_base_del_limite_del_40_por_ciento():
    """El 40 % se calcula antes de costos: el costo de ventas no lo reduce."""
    liq = _liquidar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("300000000"), costo_de_ventas=D("180000000")
        )
    )
    assert liq.valor("CG-BASE-LIMITE") == D("300000000")


# ---------------------------------------------------------------------------
# Todo junto
# ---------------------------------------------------------------------------


def test_un_comerciante_con_todo_activado_liquida_de_forma_coherente():
    liq = _liquidar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("600000000"),
            costo_de_ventas=D("300000000"),
            costos_y_gastos=D("50000000"),
        ),
        activos_depreciables=[
            ActivoDepreciable("Camioneta", D("120000000"),
                              "FLOTA_Y_EQUIPO_DE_TRANSPORTE_TERRESTRE", 10),
        ],
        perdidas_compensables=[PerdidaCompensable(2023, "NO_LABORAL", D("20000000"))],
        bancarizacion=InsumosBancarizacion(
            total_pagos_del_anio=D("400000000"), pagos_en_efectivo=D("200000000")
        ),
        ganancias_ocasionales=GananciasOcasionales(ingresos=D("80000000")),
        patrimonio=Patrimonio(patrimonio_bruto=D("900000000"), deudas=D("200000000")),
        comparacion_patrimonial=InsumosComparacionPatrimonial(
            patrimonio_liquido_anterior=D("600000000")
        ),
        conceptos_depuracion=[ConceptoDepuracion("Medicina prepagada", D("9000000"), True, "Art. 387 ET")],
        numero_dependientes=2,
        retenciones_en_la_fuente=D("25000000"),
        impuesto_neto_anio_anterior=D("30000000"),
        metodo_anticipo="MENOR",
    )

    depreciacion = D("12000000.00")   # 120M ÷ 10 = 12M; tope 10 % = 12M
    assert liq.valor("DEP-TOTAL") == depreciacion
    assert liq.valor("CG-COSTOS") == D("300000000") + D("50000000") + depreciacion
    assert liq.valor("CG-COMPENSACION") == D("20000000.00")
    # Costos 362M: el 35 % (126,7M) manda sobre el 40 % de los pagos (160M).
    assert liq.valor("CG-EFECTIVO-ACEPTADO") == D("126700000.00")
    assert liq.valor("CG-EFECTIVO-RECHAZADO") == D("73300000.00")
    assert liq.valor("GO-IMPUESTO") == D("12000000.00")   # 15 % de 80M
    assert liq.valor("PAT-LIQUIDO") == D("700000000")
    assert liq.valor("TOTAL-A-CARGO") == liq.valor("IMP-RENTA") + liq.valor("GO-IMPUESTO")
    # Nada queda sin rastro, por muchos cálculos que se encadenen.
    assert [r.codigo for r in liq.renglones if not r.formula and not r.fuente_legal] == []


@pytest.mark.parametrize("anio", sorted(PARAMETROS_POR_ANIO))
def test_los_calculos_empresariales_funcionan_en_todos_los_anos_cargados(anio):
    parametros = PARAMETROS_POR_ANIO[anio]
    insumos = InsumosLiquidacion(
        anio_gravable=anio,
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("400000000"), costo_de_ventas=D("150000000")
        ),
        activos_depreciables=[
            ActivoDepreciable("Equipo", D("50000000"), "MAQUINARIA_Y_EQUIPOS", 10)
        ],
        bancarizacion=InsumosBancarizacion(
            total_pagos_del_anio=D("300000000"), pagos_en_efectivo=D("150000000")
        ),
    )
    liq = liquidar(insumos, parametros)
    assert liq.valor("DEP-TOTAL") == D("5000000.00")
    assert liq.valor("IMP-RENTA") > D("0")


# ---------------------------------------------------------------------------
# Pérdida del ejercicio: lo que no se alcanza a deducir no desaparece
# ---------------------------------------------------------------------------


def test_los_costos_que_superan_los_ingresos_se_reportan_como_perdida():
    """Truncar en cero sin avisar escondería una deducción que no se aplicó."""
    liq = _liquidar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("30000000"), costo_de_ventas=D("50000000")
        )
    )
    assert liq.valor("CG-PERDIDA-EJERCICIO-NO_LABORAL") == D("20000000")
    assert liq.valor("CG-RL-ANTES") == D("0")
    assert any("NO se dedujo este año" in d for d in liq.diagnosticos)


def test_la_depreciacion_imputada_a_una_subcedula_sin_ingresos_se_reporta():
    """Era el agujero: la deducción salía en el borrador y no restaba en ningún lado."""
    liq = _liquidar(
        trabajo=RentasDeTrabajo(ingresos_sin_vinculo_laboral=D("54000000")),
        activos_depreciables=[
            ActivoDepreciable("Camioneta", D("95000000"),
                              "FLOTA_Y_EQUIPO_DE_TRANSPORTE_TERRESTRE", 5, D("15000000"))
        ],
        cedula_depreciacion="NO_LABORAL",
    )
    assert liq.valor("DEP-TOTAL") == D("8000000.00")
    assert liq.valor("CG-PERDIDA-EJERCICIO-NO_LABORAL") == D("8000000.00")
    assert any("subcédula correcta" in d for d in liq.diagnosticos)


def test_una_subcedula_con_ingresos_suficientes_no_genera_perdida():
    liq = _liquidar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("100000000"), costo_de_ventas=D("40000000")
        )
    )
    assert liq.valor("CG-PERDIDA-EJERCICIO-NO_LABORAL") == D("0")
    assert not any("NO se dedujo" in d for d in liq.diagnosticos)
