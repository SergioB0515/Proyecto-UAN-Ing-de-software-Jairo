"""Cálculo del kardex por método de costeo (Proceso 9 de
documentacion/03-logica-proyecto.md, HU-14). Funciones puras: reciben los
movimientos de un producto y no tocan la base de datos.

Nada de lo que se calcula aquí se persiste: el costo de cada salida depende
de todo el histórico anterior, así que se recalcula reproduciendo los
movimientos en orden cronológico (fecha y, dentro del mismo día, orden de
registro). Así, registrar una compra con fecha anterior corrige el costo de
las ventas posteriores sin dejar datos guardados desactualizados.
"""
from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional

from core.excepciones import StockInsuficienteError

from ..inventario.modelos import MetodoCosteo
from .modelos import LineaKardex, TipoMovimiento

# Margen para comparar cantidades en float (ej. 0.1 + 0.2 != 0.3).
EPSILON = 1e-9


@dataclass
class MovimientoCosteo:
    """Lo mínimo de un Movimiento que necesita el costeo. Permite simular un
    movimiento que todavía no está guardado (sin id)."""

    fecha: date
    orden: float  # id del movimiento; float("inf") para uno aún no guardado
    tipo: TipoMovimiento
    cantidad: float
    valor_unitario: float
    movimiento_id: Optional[int] = None
    periodo_fiscal_id: Optional[int] = None


@dataclass
class LineaCalculada:
    """Una línea del kardex más el periodo al que pertenece el movimiento,
    para poder filtrar por periodo sin volver a la base de datos."""

    linea: LineaKardex
    periodo_fiscal_id: Optional[int]


def ordenar(movimientos: Iterable[MovimientoCosteo]) -> List[MovimientoCosteo]:
    return sorted(movimientos, key=lambda m: (m.fecha, m.orden))


def validar_stock(movimientos: Iterable[MovimientoCosteo]) -> float:
    """Reproduce las cantidades en orden cronológico y lanza
    StockInsuficienteError si en algún punto el saldo queda negativo.
    Devuelve el saldo final."""
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
    """Kardex completo del producto según su método de costeo."""
    if metodo == MetodoCosteo.PEPS:
        return _kardex_peps(ordenar(movimientos))
    return _kardex_promedio_ponderado(ordenar(movimientos))


def _kardex_peps(movimientos: List[MovimientoCosteo]) -> List[LineaCalculada]:
    """PEPS: cada entrada es una capa con su propio costo; las salidas
    consumen primero las capas más antiguas."""
    capas: deque = deque()  # [cantidad_restante, costo_unitario]
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
    """Promedio ponderado: cada entrada recalcula
    costo_promedio = saldo_valor / saldo_cantidad; las salidas se costean a
    ese promedio vigente."""
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
                # Sin unidades no puede quedar valor: evita residuos de
                # redondeo que contaminen el siguiente promedio.
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
    """Redondea residuos de float (ej. 2.9999999999 -> 3.0) y evita -0.0."""
    redondeado = round(valor, 6)
    return 0.0 if abs(redondeado) < EPSILON else redondeado
