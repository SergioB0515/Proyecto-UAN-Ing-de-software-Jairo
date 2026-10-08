"""Pruebas del motor de costeo (HU-14). Son sobre funciones puras: no
necesitan base de datos ni cliente HTTP."""
from datetime import date

import pytest

from core.excepciones import StockInsuficienteError
from modulos.inventario.modelos import MetodoCosteo
from modulos.movimientos.costeo import (
    MovimientoCosteo,
    calcular_kardex,
    validar_stock,
)
from modulos.movimientos.modelos import TipoMovimiento

E, S = TipoMovimiento.ENTRADA, TipoMovimiento.SALIDA


def _mov(orden, fecha, tipo, cantidad, valor_unitario):
    return MovimientoCosteo(
        fecha=fecha,
        orden=orden,
        tipo=tipo,
        cantidad=cantidad,
        valor_unitario=valor_unitario,
        movimiento_id=orden,
    )


# Dos compras a distinto costo y una venta que consume más de la primera capa.
MOVIMIENTOS = [
    _mov(1, date(2025, 1, 10), E, 10, 100),
    _mov(2, date(2025, 2, 10), E, 10, 120),
    _mov(3, date(2025, 3, 10), S, 15, 200),
]


def test_peps_costea_con_las_entradas_mas_antiguas():
    lineas = [c.linea for c in calcular_kardex(MetodoCosteo.PEPS, MOVIMIENTOS)]
    salida = lineas[-1]
    # 10 unidades a 100 + 5 a 120.
    assert salida.costo_total == 1600
    assert salida.costo_unitario == pytest.approx(106.67, abs=0.01)
    assert salida.precio_venta_unitario == 200
    # Quedan 5 unidades de la segunda capa.
    assert salida.saldo_cantidad == 5
    assert salida.saldo_valor == 600


def test_promedio_ponderado_recalcula_en_cada_entrada():
    lineas = [
        c.linea for c in calcular_kardex(MetodoCosteo.PROMEDIO_PONDERADO, MOVIMIENTOS)
    ]
    # Tras las dos entradas: 20 unidades por 2.200 -> promedio 110.
    assert lineas[1].saldo_valor == 2200
    salida = lineas[-1]
    assert salida.costo_unitario == 110
    assert salida.costo_total == 1650
    assert salida.saldo_cantidad == 5
    assert salida.saldo_valor == 550


def test_el_orden_es_cronologico_no_de_registro():
    # La compra barata se registró de último pero con fecha anterior: PEPS
    # debe consumirla primero.
    movimientos = [
        _mov(1, date(2025, 2, 1), E, 5, 300),
        _mov(2, date(2025, 3, 1), S, 5, 400),
        _mov(3, date(2025, 1, 1), E, 5, 100),
    ]
    lineas = [c.linea for c in calcular_kardex(MetodoCosteo.PEPS, movimientos)]
    assert [l.movimiento_id for l in lineas] == [3, 1, 2]
    assert lineas[-1].costo_total == 500


def test_promedio_sin_saldo_reinicia_el_costo():
    movimientos = [
        _mov(1, date(2025, 1, 1), E, 3, 100),
        _mov(2, date(2025, 1, 2), S, 3, 150),
        _mov(3, date(2025, 1, 3), E, 2, 400),
        _mov(4, date(2025, 1, 4), S, 1, 500),
    ]
    lineas = [
        c.linea for c in calcular_kardex(MetodoCosteo.PROMEDIO_PONDERADO, movimientos)
    ]
    assert lineas[1].saldo_valor == 0
    # El promedio nuevo es solo el de la última compra, sin arrastrar nada.
    assert lineas[-1].costo_unitario == 400


def test_cantidades_fraccionarias_no_dejan_residuos():
    movimientos = [
        _mov(1, date(2025, 1, 1), E, 0.1, 10),
        _mov(2, date(2025, 1, 2), E, 0.2, 10),
        _mov(3, date(2025, 1, 3), S, 0.3, 20),
    ]
    assert validar_stock(movimientos) == 0
    for metodo in MetodoCosteo:
        ultima = calcular_kardex(metodo, movimientos)[-1].linea
        assert ultima.saldo_cantidad == 0
        assert ultima.saldo_valor == 0


def test_validar_stock_detecta_saldo_negativo_en_el_pasado():
    # El saldo final sería 5, pero el 1 de febrero se venden 5 unidades que
    # todavía no habían entrado.
    movimientos = [
        _mov(1, date(2025, 3, 1), E, 10, 100),
        _mov(2, date(2025, 2, 1), S, 5, 200),
    ]
    with pytest.raises(StockInsuficienteError):
        validar_stock(movimientos)


def test_validar_stock_devuelve_el_saldo_final():
    assert validar_stock(MOVIMIENTOS) == 5
