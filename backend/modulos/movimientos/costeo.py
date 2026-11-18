"""Costeo de inventario: PEPS y promedio ponderado.

Entra y sale float (base y API); el cálculo intermedio es Decimal vía str
y se redondea al final, a la mitad hacia arriba.
"""

from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, List, Optional

from core.excepciones import StockInsuficienteError

from ..inventario.modelos import MetodoCosteo
from .modelos import LineaKardex, TipoMovimiento

EPSILON = Decimal("0.000000001")
CERO = Decimal("0")
_CENTAVO = Decimal("0.01")
_MICRO = Decimal("0.000001")


def _d(valor) -> Decimal:
    """float -> Decimal vía str."""
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _pesos(valor: Decimal) -> float:
    return float(valor.quantize(_CENTAVO, rounding=ROUND_HALF_UP))


@dataclass
class MovimientoCosteo:
    fecha: date
    orden: float
    tipo: TipoMovimiento
    cantidad: float
    valor_unitario: float
    movimiento_id: Optional[int] = None
    periodo_fiscal_id: Optional[int] = None


@dataclass
class LineaCalculada:
    linea: LineaKardex
    periodo_fiscal_id: Optional[int]


def ordenar(movimientos: Iterable[MovimientoCosteo]) -> List[MovimientoCosteo]:
    return sorted(movimientos, key=lambda m: (m.fecha, m.orden))


def validar_stock(movimientos: Iterable[MovimientoCosteo]) -> float:
    saldo = CERO
    for mov in ordenar(movimientos):
        cantidad = _d(mov.cantidad)
        if mov.tipo == TipoMovimiento.ENTRADA:
            saldo += cantidad
            continue
        if cantidad > saldo + EPSILON:
            raise StockInsuficienteError(
                f"Stock insuficiente al {mov.fecha.isoformat()}: se intentan "
                f"sacar {mov.cantidad:g} unidades y solo hay {float(saldo):g} disponibles"
            )
        saldo -= cantidad
    return _limpiar(saldo)


def calcular_kardex(
    metodo: MetodoCosteo, movimientos: Iterable[MovimientoCosteo]
) -> List[LineaCalculada]:
    if metodo == MetodoCosteo.PEPS:
        return _kardex_peps(ordenar(movimientos))
    return _kardex_promedio_ponderado(ordenar(movimientos))


def _kardex_peps(movimientos: List[MovimientoCosteo]) -> List[LineaCalculada]:
    capas: deque = deque()
    lineas: List[LineaCalculada] = []

    for mov in movimientos:
        cantidad, unitario = _d(mov.cantidad), _d(mov.valor_unitario)
        if mov.tipo == TipoMovimiento.ENTRADA:
            capas.append([cantidad, unitario])
            costo_total = cantidad * unitario
        else:
            restante = cantidad
            costo_total = CERO
            while restante > EPSILON:
                if not capas:
                    raise StockInsuficienteError(
                        f"Stock insuficiente al {mov.fecha.isoformat()} para "
                        f"costear la salida del movimiento {mov.movimiento_id}"
                    )
                capa = capas[0]
                tomado = min(capa[0], restante)
                costo_total += tomado * capa[1]
                capa[0] -= tomado
                restante -= tomado
                if capa[0] <= EPSILON:
                    capas.popleft()

        saldo_cantidad = sum((c[0] for c in capas), CERO)
        saldo_valor = sum((c[0] * c[1] for c in capas), CERO)
        lineas.append(_linea(mov, costo_total, saldo_cantidad, saldo_valor))

    return lineas


def _kardex_promedio_ponderado(
    movimientos: List[MovimientoCosteo],
) -> List[LineaCalculada]:
    saldo_cantidad = CERO
    saldo_valor = CERO
    lineas: List[LineaCalculada] = []

    for mov in movimientos:
        cantidad = _d(mov.cantidad)
        if mov.tipo == TipoMovimiento.ENTRADA:
            costo_total = cantidad * _d(mov.valor_unitario)
            saldo_cantidad += cantidad
            saldo_valor += costo_total
        else:
            if cantidad > saldo_cantidad + EPSILON:
                raise StockInsuficienteError(
                    f"Stock insuficiente al {mov.fecha.isoformat()} para "
                    f"costear la salida del movimiento {mov.movimiento_id}"
                )
            costo_promedio = saldo_valor / saldo_cantidad
            costo_total = cantidad * costo_promedio
            saldo_cantidad -= cantidad
            saldo_valor -= costo_total
            if saldo_cantidad <= EPSILON:
                saldo_cantidad = CERO
                saldo_valor = CERO

        lineas.append(_linea(mov, costo_total, saldo_cantidad, saldo_valor))

    return lineas


def _linea(
    mov: MovimientoCosteo,
    costo_total: Decimal,
    saldo_cantidad: Decimal,
    saldo_valor: Decimal,
) -> LineaCalculada:
    es_salida = mov.tipo == TipoMovimiento.SALIDA
    return LineaCalculada(
        linea=LineaKardex(
            movimiento_id=mov.movimiento_id or 0,
            fecha=mov.fecha,
            tipo=mov.tipo,
            cantidad=mov.cantidad,
            costo_unitario=_pesos(costo_total / _d(mov.cantidad)),
            costo_total=_pesos(costo_total),
            saldo_cantidad=_limpiar(saldo_cantidad),
            saldo_valor=_pesos(saldo_valor),
            precio_venta_unitario=mov.valor_unitario if es_salida else None,
        ),
        periodo_fiscal_id=mov.periodo_fiscal_id,
    )


def _limpiar(valor: Decimal) -> float:
    redondeado = _d(valor).quantize(_MICRO, rounding=ROUND_HALF_UP)
    return 0.0 if abs(redondeado) < EPSILON else float(redondeado)
