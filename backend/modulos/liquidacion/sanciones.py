"""Sanción por extemporaneidad (arts. 639, 640 y 641 ET).

Solo la del art. 641: la de quien presenta tarde por su cuenta, antes de que la
DIAN lo emplace. Después del emplazamiento las tarifas se duplican (art. 642) y
eso ya no es una liquidación privada corriente; este módulo no la cubre.

Los intereses de mora tampoco se calculan. Dependen de la tasa de usura que
certifica la Superintendencia Financiera cada mes (arts. 634 y 635 ET), y una
tasa desactualizada daría una cifra con apariencia exacta que no lo es.

Función pura: no consulta la base de datos ni el reloj.
"""

from core.formato import pesos
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

CERO = Decimal("0")

TARIFA_SOBRE_IMPUESTO = Decimal("0.05")       # por mes o fracción
TARIFA_SOBRE_INGRESOS = Decimal("0.005")
TOPE_SOBRE_INGRESOS = Decimal("0.05")
TARIFA_SOBRE_PATRIMONIO = Decimal("0.01")
TOPE_SOBRE_PATRIMONIO = Decimal("0.10")
TOPE_SIN_SALDO_A_FAVOR_UVT = Decimal("2500")
SANCION_MINIMA_UVT = Decimal("10")

# Reducciones del art. 640 para la sanción que liquida el propio contribuyente.
REDUCCIONES = {
    "NINGUNA": Decimal("1"),
    "AL_75": Decimal("0.75"),   # sin la misma conducta en el último año
    "AL_50": Decimal("0.50"),   # sin la misma conducta en los dos últimos años
}


@dataclass
class ResultadoSancion:
    valor: Decimal = CERO
    meses: int = 0
    base: str = ""
    formula: str = ""
    diagnosticos: List[str] = field(default_factory=list)


def meses_de_retardo(vencimiento: date, presentacion: date) -> int:
    """Meses o fracción de mes calendario entre el vencimiento y la presentación.

    El art. 641 cuenta «cada mes o fracción de mes calendario de retardo»: un
    día de retraso ya es un mes, y el segundo empieza al día siguiente de
    cumplirse el primero.
    """
    if presentacion <= vencimiento:
        return 0
    meses = (presentacion.year - vencimiento.year) * 12 + (
        presentacion.month - vencimiento.month
    )
    if presentacion.day > vencimiento.day:
        meses += 1
    return max(meses, 1)


def calcular_extemporaneidad(
    vencimiento: Optional[date],
    presentacion: Optional[date],
    impuesto_a_cargo: Decimal,
    ingresos_brutos: Decimal,
    patrimonio_liquido_anterior: Optional[Decimal],
    saldo_a_favor: Decimal,
    uvt: Decimal,
    reduccion: str = "NINGUNA",
) -> ResultadoSancion:
    if vencimiento is None or presentacion is None:
        return ResultadoSancion()
    meses = meses_de_retardo(vencimiento, presentacion)
    if meses == 0:
        return ResultadoSancion()

    resultado = ResultadoSancion(meses=meses)
    minima = SANCION_MINIMA_UVT * uvt

    if impuesto_a_cargo > CERO:
        bruta = min(impuesto_a_cargo * TARIFA_SOBRE_IMPUESTO * meses, impuesto_a_cargo)
        resultado.base = "IMPUESTO"
        resultado.formula = (
            f"5 % × {meses} mes(es) o fracción × impuesto a cargo "
            f"{pesos(impuesto_a_cargo)}, sin exceder el 100 % del impuesto"
        )
    else:
        tope_alterno = (
            saldo_a_favor * 2 if saldo_a_favor > CERO
            else TOPE_SIN_SALDO_A_FAVOR_UVT * uvt
        )
        texto_tope = (
            f"el doble del saldo a favor ({pesos(saldo_a_favor * 2)})"
            if saldo_a_favor > CERO
            else f"{TOPE_SIN_SALDO_A_FAVOR_UVT} UVT ({pesos(tope_alterno)})"
        )
        if ingresos_brutos > CERO:
            bruta = min(
                ingresos_brutos * TARIFA_SOBRE_INGRESOS * meses,
                ingresos_brutos * TOPE_SOBRE_INGRESOS,
                tope_alterno,
            )
            resultado.base = "INGRESOS"
            resultado.formula = (
                f"Sin impuesto a cargo: 0,5 % × {meses} mes(es) o fracción × ingresos "
                f"brutos {pesos(ingresos_brutos)}, sin exceder el 5 % de los ingresos "
                f"ni {texto_tope}"
            )
        elif patrimonio_liquido_anterior and patrimonio_liquido_anterior > CERO:
            bruta = min(
                patrimonio_liquido_anterior * TARIFA_SOBRE_PATRIMONIO * meses,
                patrimonio_liquido_anterior * TOPE_SOBRE_PATRIMONIO,
                tope_alterno,
            )
            resultado.base = "PATRIMONIO"
            resultado.formula = (
                f"Sin impuesto a cargo ni ingresos: 1 % × {meses} mes(es) o fracción × "
                f"patrimonio líquido del año anterior "
                f"{pesos(patrimonio_liquido_anterior)}, sin exceder el 10 % ni {texto_tope}"
            )
        else:
            bruta = CERO
            resultado.base = "MINIMA"
            resultado.formula = (
                "Sin impuesto a cargo, sin ingresos y sin patrimonio líquido del año "
                "anterior registrado: aplica la sanción mínima"
            )

    factor = REDUCCIONES.get(reduccion, Decimal("1"))
    if factor != Decimal("1"):
        resultado.formula += (
            f"; reducida al {int(factor * 100)} % por el art. 640 ET"
        )
    valor = bruta * factor
    if valor < minima:
        resultado.formula += (
            f"; se eleva a la sanción mínima de {SANCION_MINIMA_UVT} UVT "
            f"({pesos(minima)})"
        )
        valor = minima
    resultado.valor = valor.quantize(Decimal("0.01"))
    return resultado
