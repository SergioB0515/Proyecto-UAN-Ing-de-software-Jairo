"""La cédula general como grilla de cuatro columnas del formulario 210.

Cada prueba fija una regla del instructivo oficial del formulario 210 del año
gravable 2024, citada en su propio docstring. Son las reglas que no se deducen
del Estatuto leyendo los artículos: están solo en el instructivo, y acertar el
impuesto total sin acertarlas deja casillas que el contribuyente no puede
transcribir.
"""

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


# ---------------------------------------------------------------------------
# El reparto del límite entre columnas
# ---------------------------------------------------------------------------


def test_el_limite_se_reparte_en_cascada_no_a_prorrata():
    """Instructivo, cálculo de las rentas exentas y deducciones imputables:
    «se distribuirá (…) primero a las Rentas de trabajo, segundo a las Rentas
    de trabajo que no provengan de una relación laboral (…), después a las
    Rentas de capital y por último a las Rentas no laborales, hasta agotar el
    valor total».

    Un reparto a prorrata daría el mismo impuesto y casillas distintas a las
    del servicio de diligenciamiento de la DIAN.
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
    # 40 % de 200.000.000 = 80.000.000, mayor que los 60.000.000 solicitados:
    # ambas columnas caben enteras y la cascada no tiene que recortar.
    assert resultado.limitadas_total == D("60000000")

    # Con el cupo recortado, la primera columna se lleva todo lo que puede.
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
    # 40 % de 100.000.000 = 40.000.000 para repartir entre dos columnas que
    # pidieron 30.000.000 cada una. En cascada: 30.000.000 a trabajo y los
    # 10.000.000 restantes a capital. A prorrata serían 20 y 20.
    casillas = _casillas(recortado)
    assert recortado.limitadas_total == D("40000000")
    assert casillas[41] == D("30000000")
    assert casillas[69] == D("10000000")


def test_una_columna_no_puede_restar_mas_que_su_propia_renta_liquida():
    """Instructivo casilla 69: el valor distribuido no puede «superar el valor
    de la suma de las casillas 61 (Renta líquida de las Rentas de capital) y 62
    (Rentas líquidas pasivas – ECE)».

    Sin este techo una columna quedaría en negativo y la grilla no cuadraría
    con el total.
    """
    resultado = _depurar(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000")),
        capital=RentasPorSubcedula(ingresos_brutos=D("10000000")),
        conceptos=[
            ConceptoDepuracion("Deducción de capital", D("40000000"), True,
                               "Art. 119 ET", None, CAPITAL, DEDUCCION_OTRA),
        ],
    )
    casillas = _casillas(resultado)
    assert casillas[69] == D("10000000")          # topada en la renta líquida
    assert 73 not in casillas                      # la columna queda en cero
    assert any("no permite imputar más de la renta líquida" in d
               for d in resultado.diagnosticos)


def test_una_deduccion_sin_subcedula_no_se_pierde_cuando_no_hay_renta_de_trabajo():
    """Imputar por omisión a rentas de trabajo destruiría la deducción de quien
    solo tiene rentas no laborales, porque ninguna columna puede restar más que
    su propia renta líquida.
    """
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(ingresos_brutos=D("100000000")),
        conceptos=[
            ConceptoDepuracion("Intereses de vivienda", D("20000000"), True,
                               "Art. 119 ET", None, None, DEDUCCION_VIVIENDA),
        ],
    )
    casillas = _casillas(resultado)
    assert casillas[83] == D("20000000")    # fila de vivienda, columna no laboral
    assert casillas[86] == D("20000000")
    assert resultado.casilla_93 == D("80000000")


# ---------------------------------------------------------------------------
# Los topes que no están en el 40 %
# ---------------------------------------------------------------------------


def test_la_adicion_por_dependientes_se_topa_en_la_renta_de_trabajo():
    """Instructivo casilla 92: «El valor de esta adición no puede ser mayor a
    la sumatoria de los valores registrados en las casillas 42 (Renta líquida
    ordinaria Rentas de trabajo) y 57».

    Un comerciante sin rentas de trabajo no tiene derecho a esta adición, por
    muchos dependientes que tenga.
    """
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
    """Instructivo casilla 92: la deducción del art. 336 num. 5 «no se
    encuentra sujeta al límite previsto en el numeral 3 (…) ni podrá dar lugar
    a pérdidas».
    """
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("100000000"), costos_y_gastos=D("95000000")
        ),
        compras=D("11951760"),   # 240 UVT de 2025
    )
    assert resultado.deduccion_compras == D("5000000")   # lo que queda de renta
    assert resultado.casilla_93 == D("0")
    assert any("no puede dar lugar a pérdidas" in d for d in resultado.diagnosticos)


def test_las_rentas_exentas_sin_limite_se_suman_encima_del_cuarenta_por_ciento():
    """Instructivo: «Al cuarenta por ciento (40%) o a las mil trescientas
    cuarenta (1.340) UVT anuales calculado anteriormente, se suman las rentas
    exentas que (…) no les son aplicados dichos límites».

    Son las de los nums. 6 a 9 del art. 206, el art. 206-1, los nums. 3 y 4 del
    art. 207-2, los convenios de doble tributación y la Decisión 578 de la CAN.
    """
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
    # El 40 % de 100.000.000 recorta la deducción corriente a 40.000.000, y la
    # exenta del num. 7 se suma encima sin competir por ese cupo.
    assert resultado.limitadas_total == D("60000000")
    assert resultado.casilla_93 == D("40000000")


# ---------------------------------------------------------------------------
# La base del límite
# ---------------------------------------------------------------------------


def test_las_devoluciones_no_reducen_la_base_del_cuarenta_por_ciento():
    """Instructivo: se suman los ingresos brutos de las casillas 32, 43, 58 y
    74 más los ingresos pasivos ECE «y se restan los ingresos no
    constitutivos». Las devoluciones de la casilla 75 no aparecen en esa
    operación: restarlas daría un límite más bajo y un impuesto más alto que el
    que calcula la DIAN.
    """
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("100000000"), devoluciones=D("20000000")
        ),
    )
    assert resultado.base_del_limite == D("100000000")
    # Pero sí reducen la renta líquida de la columna (casilla 78).
    assert _casillas(resultado)[78] == D("80000000")
    assert _casillas(resultado)[75] == D("20000000")


def test_la_base_del_limite_no_descuenta_costos():
    """Art. 336 num. 3: el 40 % se calcula sobre los ingresos depurados de
    ingresos no constitutivos, antes de costos y gastos.
    """
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("100000000"),
            ingresos_no_constitutivos=D("10000000"),
            costos_y_gastos=D("50000000"),
        ),
    )
    assert resultado.base_del_limite == D("90000000")


# ---------------------------------------------------------------------------
# Las filas de la grilla
# ---------------------------------------------------------------------------


def test_los_aportes_afc_van_en_una_casilla_distinta_de_las_demas_exentas():
    """El formulario separa los aportes voluntarios a AFC, FVP y AVC (casillas
    35, 47, 63 y 80) de las demás rentas exentas (36, 48, 64 y 81).
    """
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
    assert casillas[37] == D("20000000")     # total rentas exentas


def test_los_intereses_de_vivienda_van_separados_de_las_demas_deducciones():
    """Casillas 38, 50, 66 y 83 para intereses de vivienda; 39, 51, 67 y 84
    para las demás deducciones imputables.
    """
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
    assert casillas[40] == D("15000000")     # total deducciones imputables


def test_los_honorarios_cambian_de_columna_segun_la_opcion_del_336_num_4():
    """Art. 336 num. 4: quien opta por restar costos y gastos de sus honorarios
    los declara en la columna de rentas de trabajo sin vínculo laboral
    (casilla 43); quien no, los suma al salario en la casilla 32.
    """
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
    """Instructivo casilla 88: la pérdida es «el resultado positivo» de restar
    los ingresos de los costos, y va en una casilla distinta de la renta
    líquida, que queda en cero.
    """
    resultado = _depurar(
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("50000000"), costos_y_gastos=D("70000000")
        ),
    )
    casillas = _casillas(resultado)
    assert casillas[88] == D("20000000")
    assert 87 not in casillas
    assert 78 not in casillas


# ---------------------------------------------------------------------------
# La aritmética entre casillas
# ---------------------------------------------------------------------------


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
    """La grilla no es una vista aparte: el total de la cédula general sale de
    ella. Si se separan, el contador transcribe casillas que no suman su propio
    impuesto.
    """
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
    # 93 = 91 − 92, y es la renta líquida de la cédula general.
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
    de_la_grilla = [r for r in liq.renglones if r.casilla]
    assert de_la_grilla
    for renglon in de_la_grilla:
        assert renglon.fuente_legal, renglon.codigo
        assert f"[{renglon.casilla}]" in renglon.nombre
