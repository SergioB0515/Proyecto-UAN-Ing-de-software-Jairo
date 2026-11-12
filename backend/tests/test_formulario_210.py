"""Pruebas del catálogo de casillas del formulario 210.

No prueban aritmética: prueban que el catálogo sea íntegro y que no se pueda
imprimir un número de casilla equivocado. Un documento que el contador va a
transcribir a MUISCA con una casilla errada es peor que uno sin casillas.
"""

import pytest

from modulos.liquidacion.formulario_210 import (
    CASILLAS_2024,
    MAPEO_2024,
    SIN_MAPEO_POR_AGREGACION,
    SUBCEDULAS,
    casilla_de,
    casilla_de_subcedula,
)
from modulos.liquidacion.motor import InsumosLiquidacion, RentasDeTrabajo, liquidar
from modulos.parametros.tablas_oficiales import PARAMETROS_POR_ANIO


def test_no_hay_dos_casillas_con_el_mismo_numero():
    assert all(numero == casilla.numero for numero, casilla in CASILLAS_2024.items())


def test_toda_casilla_declara_su_fuente():
    assert all(c.fuente for c in CASILLAS_2024.values())


def test_todas_las_casillas_vienen_del_formulario_oficial():
    assert len(CASILLAS_2024) == 114
    assert all(c.verificado for c in CASILLAS_2024.values())
    assert all("DIAN" in c.fuente for c in CASILLAS_2024.values())


def test_la_grilla_de_la_cedula_general_tiene_las_cuatro_subcedulas():
    """Cada fila conceptual se repite en una columna por subcédula."""
    assert [
        casilla_de_subcedula("Ingresos brutos", s) for s in SUBCEDULAS
    ] == [32, 43, 58, 74]
    assert [
        casilla_de_subcedula("Rentas exentas y/o deducciones imputables (limitadas)", s)
        for s in SUBCEDULAS
    ] == [41, 53, 69, 86]


def test_las_rentas_de_trabajo_con_vinculo_no_tienen_casilla_de_costos():
    """No es un hueco del catálogo: la ley no permite restarlos ahí."""
    assert casilla_de_subcedula("Costos y deducciones procedentes", "TRABAJO") is None
    assert casilla_de_subcedula("Costos y deducciones procedentes", "CAPITAL") == 60


def test_una_fila_o_subcedula_inexistente_devuelve_none_sin_reventar():
    assert casilla_de_subcedula("Fila inventada", "CAPITAL") is None
    assert casilla_de_subcedula("Ingresos brutos", "SUBCEDULA_INVENTADA") is None


def test_todo_codigo_mapeado_apunta_a_una_casilla_que_existe():
    faltantes = [c for c in MAPEO_2024.values() if c not in CASILLAS_2024]
    assert faltantes == []


def test_ningun_codigo_del_motor_mapea_a_dos_casillas():
    assert len(set(MAPEO_2024.values())) == len(MAPEO_2024)


def test_los_codigos_mapeados_existen_de_verdad_en_la_liquidacion():
    """Si el motor renombra un renglón, el mapeo queda apuntando al vacío."""
    parametros = PARAMETROS_POR_ANIO[2024]
    liq = liquidar(
        InsumosLiquidacion(
            anio_gravable=2024,
            trabajo=RentasDeTrabajo(ingresos_brutos=__import__("decimal").Decimal("200000000")),
        ),
        parametros,
    )
    emitidos = {r.codigo for r in liq.renglones}
    # Los de pensiones, dividendos, presuntiva y ganancia ocasional solo salen
    # cuando hay esos ingresos; se excluyen de esta comprobación.
    condicionales = {
        "RENTA-PRESUNTIVA", "PEN-RENTA-LIQUIDA", "DIV-RENTA-LIQUIDA",
        "GO-BASE", "GO-IMPUESTO",
    }
    huerfanos = [c for c in MAPEO_2024 if c not in emitidos and c not in condicionales]
    assert huerfanos == []


def test_un_codigo_agregado_no_mapea_y_explica_por_que():
    """No se le puede asignar una casilla a un valor que el formulario separa."""
    for codigo, razon in SIN_MAPEO_POR_AGREGACION.items():
        assert codigo not in MAPEO_2024
        assert casilla_de(codigo, 2024) is None
        assert razon


@pytest.mark.parametrize(
    "codigo, numero",
    [("PAT-BRUTO", 29), ("PAT-LIQUIDO", 31), ("IMP-NETO-RENTA", 126), ("IMP-NETO", 129),
     ("SALDO-A-PAGAR", 136)],
)
def test_casillas_clave(codigo, numero):
    assert casilla_de(codigo, 2024).numero == numero


def test_un_ano_sin_numeracion_propia_cae_en_la_de_2024():
    """Es deliberado, y el exportado lo advierte: la DIAN puede renumerar."""
    assert casilla_de("SALDO-A-PAGAR", 2026).numero == 136
