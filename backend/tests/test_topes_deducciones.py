"""Pruebas de los topes propios de cada deducción.

El motor aplicaba el límite general del art. 336 pero ignoraba el techo propio
de cada concepto. El efecto era silencioso: una deducción improcedente entraba
a la bolsa, el límite general la tapaba y el total parecía razonable. Cuando el
límite general no alcanzaba a morder, el impuesto salía más bajo de lo debido.
Estas pruebas vigilan que el orden sea el de la ley: primero el tope propio,
después el límite general.
"""

from decimal import Decimal as D

import pytest

from modulos.liquidacion.motor import (
    ConceptoDepuracion,
    InsumosLiquidacion,
    RentasDeTrabajo,
    RentasPorSubcedula,
    liquidar,
)
from modulos.parametros.tablas_oficiales import PARAMETROS_POR_ANIO

P = PARAMETROS_POR_ANIO[2025]
UVT = P.uvt


def _liquidar(conceptos, ingresos=D("400000000")):
    return liquidar(
        InsumosLiquidacion(
            anio_gravable=2025,
            trabajo=RentasDeTrabajo(ingresos_brutos=ingresos),
            conceptos_depuracion=conceptos,
        ),
        P,
    )


def _liquidar_no_laboral(conceptos, ingresos=D("500000000")):
    """Sin rentas de trabajo no hay exención del 25 %, así que la bolsa de
    conceptos limitables es solo lo solicitado y el efecto del tope propio se
    puede aislar."""
    return liquidar(
        InsumosLiquidacion(
            anio_gravable=2025,
            no_laborales=RentasPorSubcedula(ingresos_brutos=ingresos),
            conceptos_depuracion=conceptos,
        ),
        P,
    )


def _concepto(nombre, valor, codigo):
    return ConceptoDepuracion(nombre, valor, True, "", codigo_tope=codigo)


# ---------------------------------------------------------------------------
# Topes individuales
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "codigo, uvt, mensual",
    [
        ("INTERESES_VIVIENDA", D("1200"), False),
        ("INTERESES_ICETEX", D("100"), False),
        ("MEDICINA_PREPAGADA", D("16"), True),
    ],
)
def test_cada_concepto_se_recorta_a_su_tope(codigo, uvt, mensual):
    tope = uvt * UVT * (D("12") if mensual else D("1"))
    liq = _liquidar([_concepto("Concepto", tope * 3, codigo)])
    renglon = next(r for r in liq.renglones if r.codigo.startswith("CG-TOPE-"))
    assert renglon.valor == tope.quantize(D("0.01"))
    assert any("tope propio del concepto" in d for d in liq.diagnosticos)


def test_un_concepto_dentro_de_su_tope_no_se_toca_ni_se_avisa():
    liq = _liquidar([_concepto("Intereses de vivienda", D("10000000"), "INTERESES_VIVIENDA")])
    assert not any(r.codigo.startswith("CG-TOPE-") for r in liq.renglones)
    assert not any("tope propio" in d for d in liq.diagnosticos)


def test_una_deduccion_escrita_a_mano_no_recibe_tope_inventado():
    """Sin código de catálogo el motor no conoce el techo y no debe suponerlo."""
    liq = _liquidar([ConceptoDepuracion("Concepto raro", D("500000000"), True, "")])
    assert not any(r.codigo.startswith("CG-TOPE-") for r in liq.renglones)


def test_el_tope_porcentual_manda_cuando_es_menor_que_el_de_uvt():
    """Dependientes del art. 387: 10 % del ingreso con techo de 32 UVT mensuales."""
    ingresos = D("50000000")
    liq = _liquidar(
        [_concepto("Dependientes", D("40000000"), "DEPENDIENTES_387")], ingresos=ingresos
    )
    renglon = next(r for r in liq.renglones if r.codigo.startswith("CG-TOPE-"))
    assert renglon.valor == D("5000000.00")  # 10 % de 50.000.000


def test_el_tope_en_uvt_manda_cuando_el_porcentaje_da_mas():
    ingresos = D("900000000")
    liq = _liquidar(
        [_concepto("Dependientes", D("90000000"), "DEPENDIENTES_387")], ingresos=ingresos
    )
    renglon = next(r for r in liq.renglones if r.codigo.startswith("CG-TOPE-"))
    assert renglon.valor == (D("32") * D("12") * UVT).quantize(D("0.01"))


# ---------------------------------------------------------------------------
# Tope compartido entre AFC y pensión voluntaria
# ---------------------------------------------------------------------------


def test_afc_y_pension_voluntaria_comparten_un_solo_tope():
    """3.800 UVT entre los dos, no 3.800 UVT cada uno."""
    ingresos = D("2000000000")  # alto, para que mande el tope en UVT
    tope = (D("3800") * UVT).quantize(D("0.01"))
    liq = _liquidar(
        [
            _concepto("Aportes voluntarios", D("150000000"), "APORTES_VOLUNTARIOS_PENSION"),
            _concepto("Ahorro AFC", D("150000000"), "AHORRO_AFC"),
        ],
        ingresos=ingresos,
    )
    grupo = next(r for r in liq.renglones if "GRUPO" in r.codigo)
    assert grupo.valor == tope
    assert any("No es un tope por concepto" in d for d in liq.diagnosticos)


def test_el_tope_compartido_se_reparte_a_prorrata():
    ingresos = D("400000000")
    limite = ingresos * D("0.30")  # 120.000.000, menor que 3.800 UVT
    liq = _liquidar(
        [
            _concepto("Aportes voluntarios", D("150000000"), "APORTES_VOLUNTARIOS_PENSION"),
            _concepto("Ahorro AFC", D("50000000"), "AHORRO_AFC"),
        ],
        ingresos=ingresos,
    )
    grupo = next(r for r in liq.renglones if "GRUPO" in r.codigo)
    assert grupo.valor == limite.quantize(D("0.01"))
    # 150/200 y 50/200 del tope
    solicitados = {r.nombre: r.valor for r in liq.renglones if r.codigo.startswith("CG-SOL-")}
    assert solicitados["Aportes voluntarios"] == D("90000000.00")
    assert solicitados["Ahorro AFC"] == D("30000000.00")


def test_si_el_grupo_cabe_en_su_tope_no_se_recorta():
    liq = _liquidar(
        [
            _concepto("Aportes voluntarios", D("10000000"), "APORTES_VOLUNTARIOS_PENSION"),
            _concepto("Ahorro AFC", D("5000000"), "AHORRO_AFC"),
        ]
    )
    assert not any("GRUPO" in r.codigo for r in liq.renglones)


# ---------------------------------------------------------------------------
# El orden: tope propio ANTES del límite general
# ---------------------------------------------------------------------------


def test_sin_el_tope_propio_el_impuesto_sale_mas_bajo_de_lo_debido():
    """Es el defecto que estas pruebas existen para impedir.

    Una deducción de 200 millones por intereses de vivienda es improcedente:
    el art. 119 la topa en 1.200 UVT. Aplicado el tope, lo aceptado queda por
    debajo del límite general, así que el límite general NO lo recorta y la
    diferencia se traslada entera al impuesto.
    """
    solicitado = D("200000000")
    con_tope = _liquidar_no_laboral(
        [_concepto("Intereses de vivienda", solicitado, "INTERESES_VIVIENDA")]
    )
    sin_tope = _liquidar_no_laboral(
        [ConceptoDepuracion("Intereses de vivienda", solicitado, True, "")]
    )

    assert con_tope.valor("CG-EXENTAS-LIMITADAS") == (D("1200") * UVT).quantize(D("0.01"))
    assert sin_tope.valor("CG-EXENTAS-LIMITADAS") == (D("1340") * UVT).quantize(D("0.01"))
    # Sin el tope se dedujeron 140 UVT de más y el impuesto salió más bajo.
    assert sin_tope.valor("IMP-RENTA") < con_tope.valor("IMP-RENTA")


def test_cuando_el_limite_general_ya_muerde_el_tope_propio_no_cambia_el_total():
    """Por esto el defecto era invisible.

    Con rentas de trabajo altas, la exención del 25 % llena la bolsa y el
    límite general recorta a 1.340 UVT con o sin tope propio: el total coincide
    y nada delata que la composición estaba mal. El tope sigue haciendo falta
    porque la composición importa —cada concepto va a una casilla distinta del
    formulario— y porque en cuanto los ingresos bajan, el total cambia.
    """
    solicitado = D("200000000")
    con_tope = _liquidar(
        [_concepto("Intereses de vivienda", solicitado, "INTERESES_VIVIENDA")],
        ingresos=D("300000000"),
    )
    sin_tope = _liquidar(
        [ConceptoDepuracion("Intereses de vivienda", solicitado, True, "")],
        ingresos=D("300000000"),
    )
    assert con_tope.valor("CG-RENTA-LIQUIDA") == sin_tope.valor("CG-RENTA-LIQUIDA")
    # Pero solo el que conoce el tope avisa de que la deducción era improcedente.
    assert any("tope propio del concepto" in d for d in con_tope.diagnosticos)
    assert not any("tope propio del concepto" in d for d in sin_tope.diagnosticos)


def test_despues_del_tope_propio_sigue_aplicando_el_limite_general():
    """Los dos límites se acumulan: pasar el primero no exime del segundo."""
    liq = _liquidar(
        [
            _concepto("Intereses de vivienda", D("90000000"), "INTERESES_VIVIENDA"),
            _concepto("Medicina prepagada", D("30000000"), "MEDICINA_PREPAGADA"),
        ]
    )
    assert any("tope propio del concepto" in d for d in liq.diagnosticos)
    assert any("art. 336 num. 3" in d for d in liq.diagnosticos)
    assert liq.valor("CG-EXENTAS-LIMITADAS") == (D("1340") * UVT).quantize(D("0.01"))


def test_todos_los_renglones_de_tope_llevan_su_norma():
    liq = _liquidar(
        [_concepto("Intereses de vivienda", D("90000000"), "INTERESES_VIVIENDA")]
    )
    for renglon in (r for r in liq.renglones if r.codigo.startswith("CG-TOPE-")):
        assert renglon.fuente_legal
        assert renglon.formula


@pytest.mark.parametrize("anio", sorted(PARAMETROS_POR_ANIO))
def test_todos_los_anos_traen_los_topes_cargados(anio):
    topes = PARAMETROS_POR_ANIO[anio].topes_deducciones
    assert {"INTERESES_VIVIENDA", "MEDICINA_PREPAGADA", "AHORRO_AFC"} <= set(topes)
    assert all(t.fuente_legal for t in topes.values())
