"""Sanción por extemporaneidad, arts. 639 a 641 ET."""

from datetime import date
from decimal import Decimal as D

import pytest

from modulos.liquidacion.motor import (
    InsumosLiquidacion,
    Patrimonio,
    RentasDeTrabajo,
    RentasPorSubcedula,
    liquidar,
)
from modulos.liquidacion.calculos_empresariales import ActivoDepreciable, InsumosBancarizacion
from modulos.liquidacion.sanciones import calcular_extemporaneidad, meses_de_retardo
from modulos.parametros.tablas_oficiales import PARAMETROS_POR_ANIO

UVT = D("52374")
VENCE = date(2026, 8, 12)


@pytest.mark.parametrize("presenta, meses", [
    (date(2026, 8, 12), 0),     # el mismo día no hay retardo
    (date(2026, 8, 13), 1),     # un día ya es un mes
    (date(2026, 9, 12), 1),     # se cumple el primer mes
    (date(2026, 9, 13), 2),     # y empieza el segundo
    (date(2027, 1, 5), 5),
    (date(2027, 8, 12), 12),
])
def test_cada_mes_o_fraccion_cuenta(presenta, meses):
    assert meses_de_retardo(VENCE, presenta) == meses


def _sancion(**kw):
    base = dict(
        vencimiento=VENCE, presentacion=date(2026, 10, 20), impuesto_a_cargo=D("0"),
        ingresos_brutos=D("0"), patrimonio_liquido_anterior=None,
        saldo_a_favor=D("0"), uvt=UVT,
    )
    base.update(kw)
    return calcular_extemporaneidad(**base)


def test_con_impuesto_a_cargo_es_el_5_por_ciento_por_mes():
    s = _sancion(impuesto_a_cargo=D("20000000"))          # 3 meses
    assert s.meses == 3
    assert s.valor == D("3000000.00")
    assert s.base == "IMPUESTO"


def test_no_puede_pasar_del_100_por_ciento_del_impuesto():
    s = _sancion(impuesto_a_cargo=D("20000000"), presentacion=date(2029, 8, 13))
    assert s.valor == D("20000000.00")


def test_sin_impuesto_se_liquida_sobre_los_ingresos_con_sus_topes():
    s = _sancion(ingresos_brutos=D("100000000"))          # 0,5 % × 3 meses
    assert s.valor == D("1500000.00")
    assert s.base == "INGRESOS"
    # Con saldo a favor, el tope es su doble.
    s = _sancion(ingresos_brutos=D("100000000"), saldo_a_favor=D("600000"))
    assert s.valor == D("1200000.00")
    # Sin saldo a favor, 2.500 UVT.
    s = _sancion(ingresos_brutos=D("90000000000"))
    assert s.valor == D("2500") * UVT


def test_sin_impuesto_ni_ingresos_se_liquida_sobre_el_patrimonio_anterior():
    s = _sancion(patrimonio_liquido_anterior=D("200000000"))
    assert s.valor == D("6000000.00")                      # 1 % × 3 meses
    assert s.base == "PATRIMONIO"


def test_nunca_baja_de_la_sancion_minima():
    s = _sancion(impuesto_a_cargo=D("100000"), presentacion=date(2026, 8, 13))
    assert s.valor == D("10") * UVT
    assert "sanción mínima" in s.formula


def test_la_reduccion_del_640_no_perfora_la_minima():
    s = _sancion(impuesto_a_cargo=D("20000000"), reduccion="AL_50")
    assert s.valor == D("1500000.00")
    s = _sancion(impuesto_a_cargo=D("2000000"), presentacion=date(2026, 8, 13),
                 reduccion="AL_50")
    assert s.valor == D("10") * UVT


def test_a_tiempo_o_sin_fechas_no_hay_sancion():
    assert _sancion(presentacion=VENCE).valor == D("0")
    assert _sancion(vencimiento=None).valor == D("0")
    assert _sancion(presentacion=None).valor == D("0")


def test_la_sancion_entra_en_la_135_y_sube_el_total_a_pagar():
    P = PARAMETROS_POR_ANIO[2025]
    def con(sancion):
        return liquidar(InsumosLiquidacion(
            anio_gravable=2025,
            trabajo=RentasDeTrabajo(ingresos_brutos=D("200000000")),
            patrimonio=Patrimonio(patrimonio_bruto=D("100000000")),
            sanciones=D(sancion),
        ), P)
    sin, con_sancion = con("0"), con("1500000")
    c = {r.casilla: r.valor for r in con_sancion.renglones if r.casilla}
    assert c[135] == D("1500000")
    assert c[136] == c[134] + c[135]
    assert c[134] == sin.valor("SALDO-A-PAGAR")
    assert 135 not in {r.casilla for r in sin.renglones}


def test_liquidar_dos_veces_los_mismos_insumos_da_lo_mismo():
    """El motor sumaba la depreciación y restaba el efectivo rechazado sobre los
    propios insumos: la segunda liquidación salía distinta de la primera.
    """
    P = PARAMETROS_POR_ANIO[2025]
    insumos = InsumosLiquidacion(
        anio_gravable=2025,
        no_laborales=RentasPorSubcedula(
            ingresos_brutos=D("400000000"), costos_y_gastos=D("150000000")
        ),
        activos_depreciables=[ActivoDepreciable(
            "Camioneta", D("120000000"), "FLOTA_Y_EQUIPO_DE_TRANSPORTE_TERRESTRE", 10)],
        bancarizacion=InsumosBancarizacion(
            total_pagos_del_anio=D("200000000"), pagos_en_efectivo=D("150000000")),
        patrimonio=Patrimonio(patrimonio_bruto=D("300000000")),
    )
    primera, segunda = liquidar(insumos, P), liquidar(insumos, P)
    assert [(r.codigo, r.valor) for r in primera.renglones] == \
           [(r.codigo, r.valor) for r in segunda.renglones]
    assert insumos.no_laborales.depreciacion == D("0")
