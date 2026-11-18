"""Grilla de la cédula general. Cada prueba cita la regla del instructivo del 210."""

from decimal import Decimal as D

import pytest

from modulos.liquidacion.cedula_general import (
    CAPITAL,
    DEDUCCION_OTRA,
    DEDUCCION_VIVIENDA,
    EXENTA_AFC,
    EXENTA_OTRA,
    NO_LABORAL,
    SIN_VINCULO,
    SUBCEDULAS,
    TRABAJO,
    casillas_de,
    depurar,
)
from modulos.liquidacion.motor import (
    ConceptoDepuracion,
    InsumosLiquidacion,
    Patrimonio,
    RentasDeTrabajo,
    RentasPorSubcedula,
    liquidar,
)
from modulos.parametros.tablas_oficiales import PARAMETROS_POR_ANIO

P = PARAMETROS_POR_ANIO[2025]
UVT = P.uvt


def _depurar(trabajo=None, capital=None, no_laborales=None, conceptos=None,
             exenta_25=D("0"), dependientes=D("0"), compras=D("0")):
    return depurar(
        trabajo or RentasDeTrabajo(),
        capital or RentasPorSubcedula(),
        no_laborales or RentasPorSubcedula(),
        conceptos or [],
        exenta_25,
        dependientes,
        compras,
        D("0"),
        P,
    )


def _casillas(resultado) -> dict:
    return {numero: valor for numero, _, valor in casillas_de(resultado)}


# Reparto del límite entre columnas


def test_el_limite_se_reparte_en_cascada_no_a_prorrata():
    """Instructivo: el límite se distribuye en cascada (trabajo, sin vínculo,
    capital, no laborales).
    """
    resultado = _depurar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")),
        capital=RentasPorSubcedula(ingresos_brutos=D("100000000")),
        conceptos=[
            ConceptoDepuracion("Deducción de trabajo", D("30000000"), True,
                               "Art. 387 ET", None, TRABAJO, DEDUCCION_OTRA),
            ConceptoDepuracion("Deducción de capital", D("30000000"), True,
                               "Art. 119 ET", None, CAPITAL, DEDUCCION_OTRA),
        ],
    )
    # 40 % de 200 M = 80 M > 60 M solicitados: no hay recorte.
    assert resultado.limitadas_total == D("60000000")

    # Con recorte, la primera columna toma todo lo que puede.
    recortado = _depurar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("50000000")),
        capital=RentasPorSubcedula(ingresos_brutos=D("50000000")),
        conceptos=[
            ConceptoDepuracion("Deducción de trabajo", D("30000000"), True,
                               "Art. 387 ET", None, TRABAJO, DEDUCCION_OTRA),
            ConceptoDepuracion("Deducción de capital", D("30000000"), True,
                               "Art. 119 ET", None, CAPITAL, DEDUCCION_OTRA),
        ],
    )
    # Cupo de 40 M, dos columnas de 30 M: 30 a trabajo, 10 a capital (no 20 y 20).
    casillas = _casillas(recortado)
    assert recortado.limitadas_total == D("40000000")
    assert casillas[41] == D("30000000")
    assert casillas[69] == D("10000000")


def test_una_columna_no_puede_restar_mas_que_su_propia_renta_liquida():
    """Instructivo casilla 69: tope en casillas 61 + 62."""
    resultado = _depurar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000")),
        capital=RentasPorSubcedula(ingresos_brutos=D("10000000")),
        conceptos=[
            ConceptoDepuracion("Deducción de capital", D("40000000"), True,
                               "Art. 119 ET", None, CAPITAL, DEDUCCION_OTRA),
        ],
    )
    casillas = _casillas(resultado)
    assert casillas[69] == D("10000000")  # topada en la renta líquida
    assert 73 not in casillas  # columna en cero
    assert any("no permite imputar más de la renta líquida" in d
               for d in resultado.diagnosticos)


def test_una_deduccion_sin_subcedula_no_se_pierde_cuando_no_hay_renta_de_trabajo():
    """Sin subcédula y sin rentas de trabajo, la deducción va a la columna con renta."""
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(ingresos_brutos=D("100000000")),
        conceptos=[
            ConceptoDepuracion("Intereses de vivienda", D("20000000"), True,
                               "Art. 119 ET", None, None, DEDUCCION_VIVIENDA),
        ],
    )
    casillas = _casillas(resultado)
    assert casillas[83] == D("20000000")  # fila de vivienda, columna no laboral
    assert casillas[86] == D("20000000")
    assert resultado.casilla_93 == D("80000000")


# Topes fuera del 40 %


def test_la_adicion_por_dependientes_se_topa_en_la_renta_de_trabajo():
    """Instructivo casilla 92: dependientes topados en casillas 42 + 57."""
    comerciante = _depurar(
        no_laborales=RentasPorSubcedula(ingresos_brutos=D("300000000")),
        dependientes=D("7171056"),
    )
    assert comerciante.deduccion_dependientes == D("0")
    assert any("casillas 42 y 57" in d for d in comerciante.diagnosticos)

    asalariado = _depurar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("300000000")),
        dependientes=D("7171056"),
    )
    assert asalariado.deduccion_dependientes == D("7171056")
    assert asalariado.diagnosticos == []


def test_el_uno_por_ciento_de_compras_no_puede_generar_perdida():
    """Instructivo casilla 92: el 1 % de compras no tiene límite del num. 3 ni genera pérdida."""
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("100000000"), costos_y_gastos=D("95000000")
        ),
        compras=D("11951760"),  # 240 UVT de 2025
    )
    assert resultado.deduccion_compras == D("5000000")  # renta restante
    assert resultado.casilla_93 == D("0")
    assert any("no puede dar lugar a pérdidas" in d for d in resultado.diagnosticos)


def test_las_rentas_exentas_sin_limite_se_suman_encima_del_cuarenta_por_ciento():
    """Instructivo: exentas fuera del límite se suman sobre el 40 % / 1.340 UVT."""
    resultado = _depurar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")),
        conceptos=[
            ConceptoDepuracion("Deducción corriente", D("50000000"), True,
                               "Art. 387 ET", None, TRABAJO, DEDUCCION_OTRA),
            ConceptoDepuracion("Renta exenta art. 206 num. 7", D("20000000"),
                               False, "Art. 206 num. 7 ET", None, TRABAJO,
                               EXENTA_OTRA),
        ],
    )
    # 40 % de 100 M recorta a 40 M; la exenta del num. 7 se suma encima.
    assert resultado.limitadas_total == D("60000000")
    assert resultado.casilla_93 == D("40000000")


# Base del límite


def test_las_devoluciones_no_reducen_la_base_del_cuarenta_por_ciento():
    """Instructivo: la base resta INCRNGO, no devoluciones (casilla 75)."""
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("100000000"), devoluciones=D("20000000")
        ),
    )
    assert resultado.base_del_limite == D("100000000")
    # Sí reducen la renta líquida (casilla 78).
    assert _casillas(resultado)[78] == D("80000000")
    assert _casillas(resultado)[75] == D("20000000")


def test_la_base_del_limite_no_descuenta_costos():
    """Art. 336 num. 3: base antes de costos y gastos."""
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("100000000"),
            ingresos_no_constitutivos=D("10000000"),
            costos_y_gastos=D("50000000"),
        ),
    )
    assert resultado.base_del_limite == D("90000000")


# Filas de la grilla


def test_los_aportes_afc_van_en_una_casilla_distinta_de_las_demas_exentas():
    """AFC/FVP/AVC (35, 47, 63, 80) separadas de otras exentas (36, 48, 64, 81)."""
    resultado = _depurar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000")),
        conceptos=[
            ConceptoDepuracion("Aportes voluntarios AFC", D("15000000"), True,
                               "Art. 126-4 ET", None, TRABAJO, EXENTA_AFC),
            ConceptoDepuracion("Otra renta exenta", D("5000000"), True,
                               "Art. 206 ET", None, TRABAJO, EXENTA_OTRA),
        ],
    )
    casillas = _casillas(resultado)
    assert casillas[35] == D("15000000")
    assert casillas[36] == D("5000000")
    assert casillas[37] == D("20000000")  # total rentas exentas


def test_los_intereses_de_vivienda_van_separados_de_las_demas_deducciones():
    """Vivienda en 38, 50, 66, 83; otras deducciones en 39, 51, 67, 84."""
    resultado = _depurar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000")),
        conceptos=[
            ConceptoDepuracion("Intereses de vivienda", D("12000000"), True,
                               "Art. 119 ET", None, TRABAJO, DEDUCCION_VIVIENDA),
            ConceptoDepuracion("GMF deducible", D("3000000"), True,
                               "Art. 115 ET", None, TRABAJO, DEDUCCION_OTRA),
        ],
    )
    casillas = _casillas(resultado)
    assert casillas[38] == D("12000000")
    assert casillas[39] == D("3000000")
    assert casillas[40] == D("15000000")  # total deducciones imputables


def test_los_honorarios_cambian_de_columna_segun_la_opcion_del_336_num_4():
    """Art. 336 num. 4: honorarios con opción de costos en casilla 43; sin ella, en 32."""
    sin_costos = _depurar(
        trabajo=RentasDeTrabajo(
            ingresos_brutos=D("50000000"),
            ingresos_sin_vinculo_laboral=D("80000000"),
            opta_por_costos_y_gastos=False,
        ),
    )
    assert _casillas(sin_costos)[32] == D("130000000")
    assert 43 not in _casillas(sin_costos)

    con_costos = _depurar(
        trabajo=RentasDeTrabajo(
            ingresos_brutos=D("50000000"),
            ingresos_sin_vinculo_laboral=D("80000000"),
            costos_y_gastos_sin_vinculo_laboral=D("30000000"),
            opta_por_costos_y_gastos=True,
        ),
    )
    casillas = _casillas(con_costos)
    assert casillas[32] == D("50000000")
    assert casillas[43] == D("80000000")
    assert casillas[45] == D("30000000")
    assert casillas[46] == D("50000000")


def test_la_perdida_del_ejercicio_va_en_su_propia_casilla_y_no_en_la_renta():
    """Instructivo casilla 88: pérdida en casilla propia; renta líquida en cero."""
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("50000000"), costos_y_gastos=D("70000000")
        ),
    )
    casillas = _casillas(resultado)
    assert casillas[88] == D("20000000")
    assert 87 not in casillas
    assert 78 not in casillas


# Aritmética entre casillas


def test_la_casilla_91_es_la_suma_que_manda_el_instructivo():
    """Casilla 91 = 41 + 42 + 53 + 57 + 69 + 73 + 86 + 90."""
    resultado = _depurar(
        trabajo=RentasDeTrabajo(
            ingresos_brutos=D("120000000"),
            ingresos_sin_vinculo_laboral=D("60000000"),
            costos_y_gastos_sin_vinculo_laboral=D("20000000"),
            opta_por_costos_y_gastos=True,
        ),
        capital=RentasPorSubcedula(ingresos_brutos=D("40000000")),
        no_laborales=RentasPorSubcedula(ingresos_brutos=D("30000000")),
        conceptos=[
            ConceptoDepuracion("Intereses de vivienda", D("25000000"), True,
                               "Art. 119 ET", None, None, DEDUCCION_VIVIENDA),
        ],
    )
    casillas = _casillas(resultado)
    esperado = sum(
        (casillas.get(n, D("0")) for n in (41, 42, 53, 57, 69, 73, 86, 90)), D("0")
    )
    assert resultado.casilla_91 == esperado


def test_la_casilla_93_es_la_91_menos_la_92():
    resultado = _depurar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("150000000")),
        conceptos=[
            ConceptoDepuracion("Deducción", D("20000000"), True, "Art. 387 ET",
                               None, TRABAJO, DEDUCCION_OTRA),
        ],
        dependientes=D("3585528"),
        compras=D("2000000"),
    )
    assert resultado.casilla_92 == (
        resultado.deduccion_compras
        + resultado.limitadas_total
        + resultado.deduccion_dependientes
    )
    assert resultado.casilla_93 == resultado.casilla_91 - resultado.casilla_92


def test_la_grilla_cuadra_con_el_total_que_liquida_el_motor():
    """El total de la cédula general sale de la grilla."""
    insumos = InsumosLiquidacion(
        anio_gravable=2025,
        trabajo=RentasDeTrabajo(
            ingresos_brutos=D("180000000"), aportes_obligatorios_salud=D("7200000")
        ),
        capital=RentasPorSubcedula(
            ingresos_brutos=D("60000000"), costos_y_gastos=D("15000000")
        ),
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("90000000"), devoluciones=D("5000000"),
            costos_y_gastos=D("20000000"),
        ),
        conceptos_depuracion=[
            ConceptoDepuracion("Aportes AFC", D("18000000"), True, "Art. 126-4 ET",
                               None, TRABAJO, EXENTA_AFC),
            ConceptoDepuracion("Intereses de vivienda", D("14000000"), True,
                               "Art. 119 ET", None, TRABAJO, DEDUCCION_VIVIENDA),
        ],
        numero_dependientes=2,
        patrimonio=Patrimonio(patrimonio_bruto=D("500000000")),
    )
    liq = liquidar(insumos, P)
    casillas = {r.casilla: r.valor for r in liq.renglones if r.casilla}

    # 91 = 41 + 42 + 53 + 57 + 69 + 73 + 86 + 90
    assert casillas[91] == sum(
        (casillas.get(n, D("0")) for n in (41, 42, 53, 57, 69, 73, 86, 90)), D("0")
    )
    # 92 = 28 + 41 + 53 + 69 + 86 + 139
    assert casillas[92] == sum(
        (casillas.get(n, D("0")) for n in (28, 41, 53, 69, 86, 139)), D("0")
    )
    # 93 = 91 − 92
    assert casillas[93] == casillas[91] - casillas[92]
    assert liq.valor("CG-RENTA-LIQUIDA") == casillas[93]


@pytest.mark.parametrize("anio", sorted(PARAMETROS_POR_ANIO))
def test_la_grilla_cuadra_en_todos_los_anos_cargados(anio):
    insumos = InsumosLiquidacion(
        anio_gravable=anio,
        trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000")),
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("120000000"), costo_de_ventas=D("40000000")
        ),
        conceptos_depuracion=[
            ConceptoDepuracion("Medicina prepagada", D("9000000"), True,
                               "Art. 387 ET", "MEDICINA_PREPAGADA"),
        ],
        numero_dependientes=1,
        patrimonio=Patrimonio(patrimonio_bruto=D("400000000")),
    )
    liq = liquidar(insumos, PARAMETROS_POR_ANIO[anio])
    casillas = {r.casilla: r.valor for r in liq.renglones if r.casilla}
    assert casillas[93] == casillas[91] - casillas[92]
    assert casillas[93] >= D("0")


def test_cada_casilla_de_la_grilla_lleva_su_numero_y_su_norma():
    insumos = InsumosLiquidacion(
        anio_gravable=2025,
        trabajo=RentasDeTrabajo(ingresos_brutos=D("100000000")),
        patrimonio=Patrimonio(patrimonio_bruto=D("200000000")),
    )
    liq = liquidar(insumos, P)
    con_casilla = [r for r in liq.renglones if r.casilla]
    assert con_casilla
    for renglon in con_casilla:
        assert renglon.fuente_legal, renglon.codigo
    # Renglones de la grilla con el número en el nombre (la fila se repite por columna).
    for renglon in con_casilla:
        if renglon.codigo.startswith("CG-C"):
            assert f"[{renglon.casilla}]" in renglon.nombre
