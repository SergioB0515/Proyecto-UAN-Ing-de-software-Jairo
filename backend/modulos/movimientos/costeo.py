from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional

from core.excepciones import StockInsuficienteError

from ..inventario.modelos import MetodoCosteo
from .modelos import LineaKardex, TipoMovimiento

EPSILON = 1e-9


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
    saldo = 0.0
    for mov in ordenar(movimientos):
        if mov.tipo == TipoMovimiento.ENTRADA:
            saldo += mov.cantidad
            continue
        if mov.cantidad > saldo + EPSILON:
            raise StockInsuficienteError(
                f"Stock insuficiente al {mov.fecha.isoformat()}: se intentan "
                f"sacar {mov.cantidad:g} unidades y solo hay {saldo:g} disponibles"
            )
        saldo -= mov.cantidad
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
        if mov.tipo == TipoMovimiento.ENTRADA:
            capas.append([mov.cantidad, mov.valor_unitario])
            costo_total = mov.cantidad * mov.valor_unitario
        else:
            restante = mov.cantidad
            costo_total = 0.0
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

        saldo_cantidad = sum(c[0] for c in capas)
        saldo_valor = sum(c[0] * c[1] for c in capas)
        lineas.append(_linea(mov, costo_total, saldo_cantidad, saldo_valor))

    return lineas


def _kardex_promedio_ponderado(
    movimientos: List[MovimientoCosteo],
) -> List[LineaCalculada]:
    saldo_cantidad = 0.0
    saldo_valor = 0.0
    lineas: List[LineaCalculada] = []

    for mov in movimientos:
        if mov.tipo == TipoMovimiento.ENTRADA:
            costo_total = mov.cantidad * mov.valor_unitario
            saldo_cantidad += mov.cantidad
            saldo_valor += costo_total
        else:
            if mov.cantidad > saldo_cantidad + EPSILON:
                raise StockInsuficienteError(
                    f"Stock insuficiente al {mov.fecha.isoformat()} para "
                    f"costear la salida del movimiento {mov.movimiento_id}"
                )
            costo_promedio = saldo_valor / saldo_cantidad
            costo_total = mov.cantidad * costo_promedio
            saldo_cantidad -= mov.cantidad
            saldo_valor -= costo_total
            if saldo_cantidad <= EPSILON:
                saldo_cantidad = 0.0
                saldo_valor = 0.0

        lineas.append(_linea(mov, costo_total, saldo_cantidad, saldo_valor))

    return lineas


def _linea(
    mov: MovimientoCosteo, costo_total: float, saldo_cantidad: float, saldo_valor: float
) -> LineaCalculada:
    es_salida = mov.tipo == TipoMovimiento.SALIDA
    return LineaCalculada(
        linea=LineaKardex(
            movimiento_id=mov.movimiento_id or 0,
            fecha=mov.fecha,
            tipo=mov.tipo,
            cantidad=mov.cantidad,
            costo_unitario=round(costo_total / mov.cantidad, 2),
            costo_total=round(costo_total, 2),
            saldo_cantidad=_limpiar(saldo_cantidad),
            saldo_valor=round(_limpiar(saldo_valor), 2),
            precio_venta_unitario=mov.valor_unitario if es_salida else None,
        ),
        periodo_fiscal_id=mov.periodo_fiscal_id,
    )


def _limpiar(valor: float) -> float:
    redondeado = round(valor, 6)
    return 0.0 if abs(redondeado) < EPSILON else redondeado
