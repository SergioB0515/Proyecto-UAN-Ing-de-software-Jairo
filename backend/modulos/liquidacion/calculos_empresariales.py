"""Cálculos de la parte empresarial: depreciación, bancarización, pérdidas y
comparación patrimonial.

Viven aparte de `motor.py` por dos razones. Primera, cada uno se puede probar
y revisar por separado contra su norma, que es como lo revisaría un contador.
Segunda, `motor.py` orquesta la liquidación y ya es largo; mezclar aquí la
tabla del art. 137 lo volvería ilegible.

Todas las funciones son puras y trabajan en `Decimal`. Ninguna toca la base de
datos ni conoce un número del Estatuto: los parámetros llegan por argumento.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Tuple

from ..parametros.tablas_oficiales import ParametrosAnuales

CERO = Decimal("0")
_CENTAVO = Decimal("0.01")


def _redondear(valor: Decimal) -> Decimal:
    from .motor import redondear_pesos

    return redondear_pesos(valor)


def _no_negativo(valor: Decimal) -> Decimal:
    return valor if valor > CERO else CERO


def _pct(fraccion: Decimal) -> str:
    from .motor import porcentaje

    return porcentaje(fraccion)


# ---------------------------------------------------------------------------
# Depreciación (arts. 128 a 131 y 137 ET)
# ---------------------------------------------------------------------------


@dataclass
class ActivoDepreciable:
    """Un activo fijo con los datos que la depreciación necesita.

    `categoria` debe ser una de las claves de la tabla del art. 137. Si no lo
    es, el cálculo no adivina una tasa: devuelve un diagnóstico y excluye el
    activo, porque aplicar la tasa equivocada cambia la deducción.
    """

    descripcion: str
    costo_fiscal: Decimal
    categoria: str
    vida_util_anios: int
    valor_residual: Decimal = CERO
    meses_en_el_periodo: int = 12
    depreciacion_acumulada: Decimal = CERO


@dataclass
class ResultadoDepreciacion:
    total: Decimal = CERO
    detalle: List[Tuple[str, Decimal, str]] = field(default_factory=list)
    diagnosticos: List[str] = field(default_factory=list)


def calcular_depreciacion(
    activos: List[ActivoDepreciable], parametros: ParametrosAnuales
) -> ResultadoDepreciacion:
    """Depreciación deducible del periodo, por línea recta y topada por el art. 137.

    El art. 137 fija **tasas anuales máximas**, no vidas útiles obligatorias.
    El contribuyente puede estimar una vida útil menor —y así lo registra en su
    contabilidad—, pero fiscalmente solo deduce hasta la tasa de la tabla. Por
    eso aquí se calcula con la vida útil que registró el contador y luego se
    recorta, en vez de imponer la vida útil de la tabla.

    La base depreciable es el costo fiscal menos el valor residual, y nunca se
    deprecia más allá de esa base: un activo ya depreciado por completo deja de
    generar deducción aunque siga en uso.
    """
    resultado = ResultadoDepreciacion()

    for activo in activos:
        tasa_maxima = parametros.tasas_depreciacion.get(activo.categoria)
        if tasa_maxima is None:
            disponibles = ", ".join(sorted(parametros.tasas_depreciacion))
            resultado.diagnosticos.append(
                f"«{activo.descripcion}» tiene la categoría «{activo.categoria}», que "
                f"no está en la tabla del art. 137, así que se excluyó de la "
                f"depreciación. Categorías válidas: {disponibles}."
            )
            continue

        if activo.vida_util_anios <= 0:
            resultado.diagnosticos.append(
                f"«{activo.descripcion}» no tiene vida útil registrada; se excluyó "
                f"de la depreciación."
            )
            continue

        base = _no_negativo(activo.costo_fiscal - activo.valor_residual)
        pendiente = _no_negativo(base - activo.depreciacion_acumulada)
        if pendiente == CERO:
            resultado.diagnosticos.append(
                f"«{activo.descripcion}» ya está depreciado por completo: no genera "
                f"deducción este año."
            )
            continue

        meses = max(0, min(activo.meses_en_el_periodo, 12))
        proporcion = Decimal(meses) / Decimal(12)

        por_vida_util = base / Decimal(activo.vida_util_anios) * proporcion
        tope_fiscal = base * tasa_maxima * proporcion
        del_periodo = min(por_vida_util, tope_fiscal, pendiente)

        formula = (
            f"base ${base.quantize(_CENTAVO)} (costo fiscal − valor residual) "
            f"÷ {activo.vida_util_anios} años"
            + (f" × {meses}/12 meses" if meses != 12 else "")
            + f" = ${por_vida_util.quantize(_CENTAVO)}"
        )
        if tope_fiscal < por_vida_util:
            formula += (
                f", recortado al tope del art. 137 para {activo.categoria} "
                f"({_pct(tasa_maxima)}% anual) = "
                f"${tope_fiscal.quantize(_CENTAVO)}"
            )
            resultado.diagnosticos.append(
                f"La vida útil registrada para «{activo.descripcion}» da una "
                f"depreciación mayor a la tasa máxima del art. 137; la deducción "
                f"se recortó a ${_redondear(tope_fiscal)}. La diferencia es una "
                f"diferencia entre contabilidad y fiscal, no una pérdida."
            )
        if pendiente < min(por_vida_util, tope_fiscal):
            formula += f", limitado al saldo pendiente de ${pendiente.quantize(_CENTAVO)}"

        valor = _redondear(del_periodo)
        resultado.total += valor
        resultado.detalle.append((activo.descripcion, valor, formula))

    resultado.total = _redondear(resultado.total)
    return resultado


# ---------------------------------------------------------------------------
# Bancarización (art. 771-5 ET)
# ---------------------------------------------------------------------------


@dataclass
class PagoIndividual:
    descripcion: str
    valor: Decimal


@dataclass
class InsumosBancarizacion:
    """Totales del año. Se capturan, no se derivan.

    La aplicación solo conoce las compras de inventario; los demás pagos del
    contribuyente no están aquí. Derivar el total de lo que hay en la base
    daría una cifra incompleta que parece completa, que es peor que pedirla.
    """

    total_pagos_del_anio: Decimal = CERO
    pagos_en_efectivo: Decimal = CERO
    operaciones_individuales_en_efectivo: List[PagoIndividual] = field(
        default_factory=list
    )


@dataclass
class ResultadoBancarizacion:
    aplica: bool = False
    efectivo_aceptado: Decimal = CERO
    efectivo_rechazado: Decimal = CERO
    limite_porcentaje_pagos: Decimal = CERO
    limite_tope_uvt: Decimal = CERO
    limite_porcentaje_costos: Decimal = CERO
    operaciones_sobre_el_limite: List[PagoIndividual] = field(default_factory=list)
    formula: str = ""
    diagnosticos: List[str] = field(default_factory=list)


def calcular_bancarizacion(
    insumos: InsumosBancarizacion,
    costos_y_deducciones_totales: Decimal,
    parametros: ParametrosAnuales,
) -> ResultadoBancarizacion:
    """Parte de los pagos en efectivo que se acepta como costo o deducción.

    El límite general del parágrafo 1 es el **menor** entre tres cifras: el
    40 % de los pagos totales, 40.000 UVT y el 35 % de los costos y deducciones
    totales. Lo que exceda ese menor no es deducible.

    El límite individual del parágrafo 2 es distinto y se evalúa aparte: una
    persona natural con rentas no laborales no puede pagar en efectivo una
    operación que supere 100 UVT. Esas operaciones se listan para que el
    contador las revise; el motor no las descuenta por su cuenta, porque la
    consecuencia depende de si el pago se canalizó o no.
    """
    limite = parametros.bancarizacion
    resultado = ResultadoBancarizacion()

    tope_individual = limite.limite_individual_uvt * parametros.uvt
    resultado.operaciones_sobre_el_limite = [
        op
        for op in insumos.operaciones_individuales_en_efectivo
        if op.valor > tope_individual
    ]
    if resultado.operaciones_sobre_el_limite:
        total = sum((op.valor for op in resultado.operaciones_sobre_el_limite), CERO)
        resultado.diagnosticos.append(
            f"{len(resultado.operaciones_sobre_el_limite)} operación(es) en efectivo "
            f"por ${_redondear(total)} superan el límite individual de "
            f"{limite.limite_individual_uvt} UVT (${_redondear(tope_individual)}) del "
            f"art. 771-5 par. 2. Revíselas: si no se canalizaron por el sistema "
            f"financiero, ese costo no es procedente."
        )

    if insumos.pagos_en_efectivo <= CERO:
        return resultado

    resultado.aplica = True
    resultado.limite_porcentaje_pagos = (
        insumos.total_pagos_del_anio * limite.porcentaje_de_pagos
    )
    resultado.limite_tope_uvt = limite.tope_uvt * parametros.uvt
    resultado.limite_porcentaje_costos = (
        costos_y_deducciones_totales * limite.porcentaje_de_costos
    )

    aceptado = min(
        insumos.pagos_en_efectivo,
        resultado.limite_porcentaje_pagos,
        resultado.limite_tope_uvt,
        resultado.limite_porcentaje_costos,
    )
    resultado.efectivo_aceptado = _redondear(aceptado)
    resultado.efectivo_rechazado = _redondear(insumos.pagos_en_efectivo - aceptado)

    resultado.formula = (
        f"efectivo pagado ${insumos.pagos_en_efectivo.quantize(_CENTAVO)}; aceptado = "
        f"menor entre {_pct(limite.porcentaje_de_pagos)}% de los pagos "
        f"(${resultado.limite_porcentaje_pagos.quantize(_CENTAVO)}), "
        f"{limite.tope_uvt} UVT (${resultado.limite_tope_uvt.quantize(_CENTAVO)}) y "
        f"{_pct(limite.porcentaje_de_costos)}% de los costos y "
        f"deducciones (${resultado.limite_porcentaje_costos.quantize(_CENTAVO)})"
    )

    if resultado.efectivo_rechazado > CERO:
        cual = min(
            (resultado.limite_porcentaje_pagos, f"el {_pct(limite.porcentaje_de_pagos)}% de los pagos totales"),
            (resultado.limite_tope_uvt, f"el tope de {limite.tope_uvt} UVT"),
            (resultado.limite_porcentaje_costos, f"el {_pct(limite.porcentaje_de_costos)}% de los costos y deducciones"),
            key=lambda par: par[0],
        )[1]
        resultado.diagnosticos.append(
            f"El art. 771-5 rechaza ${resultado.efectivo_rechazado} de los pagos en "
            f"efectivo porque {cual} es la cifra menor. Ese valor se devuelve a la "
            f"renta líquida: no es un costo deducible."
        )

    return resultado


# ---------------------------------------------------------------------------
# Compensación de pérdidas fiscales
# ---------------------------------------------------------------------------


@dataclass
class PerdidaCompensable:
    anio_origen: int
    tipo_renta: str  # CAPITAL | NO_LABORAL | TRABAJO_SIN_VINCULO
    valor_disponible: Decimal


@dataclass
class ResultadoCompensacion:
    por_tipo: dict = field(default_factory=dict)
    detalle: List[Tuple[str, Decimal, str]] = field(default_factory=list)
    diagnosticos: List[str] = field(default_factory=list)


def calcular_compensacion_perdidas(
    perdidas: List[PerdidaCompensable],
    renta_liquida_por_tipo: dict,
    anio_gravable: int,
    parametros: ParametrosAnuales,
) -> ResultadoCompensacion:
    """Imputa pérdidas de años anteriores contra la renta líquida del mismo tipo.

    Dos restricciones que no se pueden saltar (art. 330 ET y art. 1.2.1.20.5
    del DUR 1625 de 2016):

    1. **Mismo tipo de renta.** Una pérdida de arrendamientos no se resta de la
       utilidad de un negocio. Las rentas de trabajo con vínculo laboral no
       admiten compensación (art. 156), ni las de pensiones ni las de
       dividendos.
    2. **Doce periodos gravables.** Una pérdida más antigua caduca y no se
       compensa, aunque siga registrada.

    Las pérdidas se consumen de la más antigua a la más reciente: es lo que
    conviene al contribuyente, porque las que están por caducar se usan primero.
    """
    resultado = ResultadoCompensacion()
    limite_anio = anio_gravable - parametros.anios_compensacion_perdidas

    vencidas = [p for p in perdidas if p.anio_origen < limite_anio]
    if vencidas:
        total = sum((p.valor_disponible for p in vencidas), CERO)
        resultado.diagnosticos.append(
            f"{len(vencidas)} pérdida(s) por ${_redondear(total)} ya superaron los "
            f"{parametros.anios_compensacion_perdidas} periodos gravables del art. 147 "
            f"y no se pueden compensar en {anio_gravable}."
        )

    vigentes = sorted(
        (p for p in perdidas if p.anio_origen >= limite_anio),
        key=lambda p: p.anio_origen,
    )

    for tipo, renta_liquida in renta_liquida_por_tipo.items():
        disponible = _no_negativo(renta_liquida)
        usado_total = CERO
        for perdida in (p for p in vigentes if p.tipo_renta == tipo):
            if disponible <= CERO:
                break
            usado = min(perdida.valor_disponible, disponible)
            if usado <= CERO:
                continue
            disponible -= usado
            usado_total += usado
            resultado.detalle.append(
                (
                    f"Pérdida de {perdida.anio_origen} ({tipo})",
                    _redondear(usado),
                    f"imputada contra la renta líquida de {tipo}; disponible era "
                    f"${perdida.valor_disponible.quantize(_CENTAVO)}",
                )
            )
        resultado.por_tipo[tipo] = _redondear(usado_total)

    no_usadas = []
    for perdida in vigentes:
        renta = _no_negativo(renta_liquida_por_tipo.get(perdida.tipo_renta, CERO))
        if renta == CERO:
            no_usadas.append(perdida)
    if no_usadas:
        resultado.diagnosticos.append(
            f"{len(no_usadas)} pérdida(s) no se compensaron porque no hay renta "
            f"líquida positiva del mismo tipo este año. Siguen disponibles para los "
            f"años siguientes dentro del plazo del art. 147."
        )

    return resultado


# ---------------------------------------------------------------------------
# Renta por comparación patrimonial (arts. 236 a 239 ET)
# ---------------------------------------------------------------------------


@dataclass
class InsumosComparacionPatrimonial:
    patrimonio_liquido_anterior: Optional[Decimal] = None
    impuestos_pagados_en_el_anio: Decimal = CERO
    justificaciones: Decimal = CERO  # valorizaciones, reajuste fiscal, herencias…
    aceptar_como_renta_gravable: bool = False


@dataclass
class ResultadoComparacionPatrimonial:
    aplica: bool = False
    incremento: Decimal = CERO
    justificado: Decimal = CERO
    diferencia: Decimal = CERO
    formula: str = ""
    diagnosticos: List[str] = field(default_factory=list)


def calcular_comparacion_patrimonial(
    insumos: InsumosComparacionPatrimonial,
    patrimonio_liquido_actual: Decimal,
    renta_gravable: Decimal,
    rentas_exentas: Decimal,
    ganancia_ocasional_neta: Decimal,
) -> ResultadoComparacionPatrimonial:
    """Compara el incremento del patrimonio líquido con lo que lo explica.

        diferencia = incremento − (renta gravable + rentas exentas
                     + ganancia ocasional neta − impuestos pagados
                     + justificaciones)

    Los impuestos pagados se restan de lo que justifica porque son una salida
    de dinero: redujeron el patrimonio y no pudieron financiar su aumento.

    **El resultado no se suma a la base por sí solo.** El art. 236 admite
    prueba en contrario: el contribuyente puede demostrar que el aumento
    obedece a causas justificativas (valorizaciones, reajuste fiscal del
    art. 70, herencias, pasivos no declarados antes). Por eso el motor lo
    calcula, lo reporta y solo lo incorpora si el contador marca que lo acepta.
    Incorporarlo automáticamente inventaría un impuesto.
    """
    resultado = ResultadoComparacionPatrimonial()
    if insumos.patrimonio_liquido_anterior is None:
        # Solo se avisa si hay patrimonio que comparar. Sin activos registrados
        # no falta nada, y un diagnóstico en cada liquidación sin patrimonio
        # sería ruido que entrena al contador a ignorar los diagnósticos.
        if patrimonio_liquido_actual > CERO:
            resultado.diagnosticos.append(
                "No hay patrimonio líquido del año anterior registrado, así que no "
                "se evaluó la comparación patrimonial (art. 236 ET). Es uno de los "
                "cruces que la DIAN hace primero."
            )
        return resultado

    resultado.aplica = True
    resultado.incremento = patrimonio_liquido_actual - insumos.patrimonio_liquido_anterior

    if resultado.incremento <= CERO:
        resultado.formula = (
            f"el patrimonio líquido no aumentó "
            f"(${patrimonio_liquido_actual.quantize(_CENTAVO)} frente a "
            f"${insumos.patrimonio_liquido_anterior.quantize(_CENTAVO)}): "
            f"no hay renta por comparación patrimonial"
        )
        return resultado

    resultado.justificado = (
        renta_gravable
        + rentas_exentas
        + ganancia_ocasional_neta
        - insumos.impuestos_pagados_en_el_anio
        + insumos.justificaciones
    )
    resultado.diferencia = _no_negativo(resultado.incremento - resultado.justificado)
    resultado.formula = (
        f"incremento ${resultado.incremento.quantize(_CENTAVO)} − (renta gravable "
        f"${renta_gravable.quantize(_CENTAVO)} + rentas exentas "
        f"${rentas_exentas.quantize(_CENTAVO)} + ganancia ocasional neta "
        f"${ganancia_ocasional_neta.quantize(_CENTAVO)} − impuestos pagados "
        f"${insumos.impuestos_pagados_en_el_anio.quantize(_CENTAVO)} + justificaciones "
        f"${insumos.justificaciones.quantize(_CENTAVO)})"
    )

    if resultado.diferencia > CERO:
        resultado.diagnosticos.append(
            f"El patrimonio líquido creció ${_redondear(resultado.incremento)} y las "
            f"rentas declaradas solo explican ${_redondear(resultado.justificado)}. "
            f"Quedan ${_redondear(resultado.diferencia)} sin justificar (art. 236 ET). "
            f"{'Se incorporó a la base gravable porque así se indicó.' if insumos.aceptar_como_renta_gravable else 'NO se incorporó a la base: la norma admite prueba en contrario. Documente la causa (valorizaciones, reajuste fiscal del art. 70, herencias, pasivos no declarados antes) o márquelo como renta gravable.'}"
        )

    return resultado
