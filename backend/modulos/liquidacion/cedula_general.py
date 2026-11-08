"""Depuración de la cédula general, subcédula por subcédula.

Por qué existe este módulo
--------------------------
El formulario 210 no pide la cédula general como un total: la pide como una
grilla de diecisiete filas por cuatro columnas —rentas de trabajo, rentas de
trabajo sin vínculo laboral, rentas de capital y rentas no laborales—, con una
casilla distinta en cada celda.

El motor venía calculando el agregado, que da el impuesto correcto pero no se
puede transcribir: el contador tenía que desagregar a mano justo lo que la
herramienta debería darle hecho.

La aritmética de cada casilla está tomada del instructivo oficial del
formulario 210 del año gravable 2024.

Reglas que no son evidentes
---------------------------
- **Los honorarios cambian de columna según la opción del art. 336 num. 4.**
  Si el contribuyente opta por restar costos y gastos, van a la columna de
  rentas de trabajo sin vínculo laboral (casilla 43). Si no, van junto con el
  salario en la columna de rentas de trabajo (casilla 32) y toman la renta
  exenta del 25 %.
- **El límite del art. 336 num. 3 es uno solo para toda la cédula general**,
  no uno por columna. Se calcula sobre el total y se reparte entre las
  columnas a prorrata de lo que cada una solicitó, que es como lo presenta el
  formulario en las casillas 41, 53, 69 y 86.
- **La deducción por dependientes y el 1 % de compras no van en ninguna
  columna.** Entran directo a la casilla 92 (casillas 139 y 28), por encima
  del límite.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..parametros.tablas_oficiales import ParametrosAnuales
from .formulario_210 import SUBCEDULAS, casilla_de_subcedula

CERO = Decimal("0")
_CENTAVO = Decimal("0.01")

TRABAJO, SIN_VINCULO, CAPITAL, NO_LABORAL = SUBCEDULAS

# Tipos de concepto, que deciden en qué casilla de la columna cae cada uno.
EXENTA_AFC = "EXENTA_AFC"
EXENTA_OTRA = "EXENTA_OTRA"
DEDUCCION_VIVIENDA = "DEDUCCION_VIVIENDA"
DEDUCCION_OTRA = "DEDUCCION_OTRA"

_NOMBRE_COLUMNA = {
    TRABAJO: "rentas de trabajo",
    SIN_VINCULO: "rentas de trabajo sin vínculo laboral",
    CAPITAL: "rentas de capital",
    NO_LABORAL: "rentas no laborales",
}

_FILA_POR_TIPO = {
    EXENTA_AFC: "Rentas exentas — aportes voluntarios AFC, FVP y AVC",
    EXENTA_OTRA: "Rentas exentas — otras rentas exentas",
    DEDUCCION_VIVIENDA: "Deducciones imputables — intereses de vivienda",
    DEDUCCION_OTRA: "Deducciones imputables — otras deducciones imputables",
}


def _no_negativo(valor: Decimal) -> Decimal:
    return valor if valor > CERO else CERO


def porcentaje_legible(fraccion: Decimal) -> str:
    """0.40 → «40». No se usa Decimal.normalize(), que devuelve 4E+1."""
    texto = f"{(fraccion * 100):f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


@dataclass
class Columna:
    """Una columna de la grilla: todos los valores de una subcédula."""

    subcedula: str
    ingresos_brutos: Decimal = CERO
    devoluciones: Decimal = CERO
    ingresos_no_constitutivos: Decimal = CERO
    costos_y_deducciones: Decimal = CERO
    rentas_pasivas_ece: Decimal = CERO
    exenta_afc: Decimal = CERO
    exenta_otra: Decimal = CERO
    deduccion_vivienda: Decimal = CERO
    deduccion_otra: Decimal = CERO
    # Parte de las rentas exentas de esta columna que la ley dejó fuera del
    # límite del art. 336 num. 3 (art. 206 nums. 6 a 9, art. 206-1, art. 207-2
    # nums. 3 y 4, convenios de doble tributación, Decisión 578 de la CAN). Se
    # imprime en la misma fila de rentas exentas, pero no compite por el cupo
    # del 40 %.
    sin_limite: Decimal = CERO
    limitadas: Decimal = CERO
    compensaciones: Decimal = CERO

    @property
    def renta_liquida(self) -> Decimal:
        return _no_negativo(
            self.ingresos_brutos
            + self.rentas_pasivas_ece
            - self.devoluciones
            - self.ingresos_no_constitutivos
            - self.costos_y_deducciones
        )

    @property
    def perdida_liquida(self) -> Decimal:
        return _no_negativo(
            self.devoluciones
            + self.ingresos_no_constitutivos
            + self.costos_y_deducciones
            - self.ingresos_brutos
            - self.rentas_pasivas_ece
        )

    @property
    def total_rentas_exentas(self) -> Decimal:
        return self.exenta_afc + self.exenta_otra

    @property
    def total_deducciones(self) -> Decimal:
        return self.deduccion_vivienda + self.deduccion_otra

    @property
    def solicitado(self) -> Decimal:
        """Todo lo solicitado en esta columna, con límite y sin él."""
        return self.total_rentas_exentas + self.total_deducciones

    @property
    def solicitado_limitable(self) -> Decimal:
        """Lo que compite por el cupo del 40 % / 1.340 UVT."""
        return _no_negativo(self.solicitado - self.sin_limite)

    @property
    def renta_liquida_ordinaria_ejercicio(self) -> Decimal:
        return _no_negativo(self.renta_liquida - self.limitadas)

    @property
    def renta_liquida_ordinaria(self) -> Decimal:
        return _no_negativo(
            self.renta_liquida_ordinaria_ejercicio - self.compensaciones
        )


@dataclass
class ResultadoCedulaGeneral:
    columnas: Dict[str, Columna]
    base_del_limite: Decimal = CERO
    limitadas_total: Decimal = CERO
    # Casilla 139. El instructivo la topa en la suma de las casillas 42 y 57:
    # la adición por dependientes no puede exceder la renta líquida ordinaria de
    # las dos columnas de rentas de trabajo.
    deduccion_dependientes: Decimal = CERO
    # Casilla 28. El art. 336 num. 5 no la sujeta al límite del num. 3, pero el
    # instructivo advierte que «no podrá dar lugar a pérdidas».
    deduccion_compras: Decimal = CERO
    rentas_gravables: Decimal = CERO
    compensacion_2018_y_anteriores: Decimal = CERO
    compensacion_exceso_presuntiva: Decimal = CERO
    diagnosticos: List[str] = field(default_factory=list)

    @property
    def casilla_91(self) -> Decimal:
        """Renta líquida cédula general = Σ(41,42,53,57,69,73,86,90)."""
        return sum(
            (c.limitadas + c.renta_liquida_ordinaria for c in self.columnas.values()),
            CERO,
        )

    @property
    def casilla_92(self) -> Decimal:
        """Rentas exentas y deducciones imputables limitadas = 28+41+53+69+86+139."""
        return (
            self.deduccion_compras
            + self.limitadas_total
            + self.deduccion_dependientes
        )

    @property
    def casilla_93(self) -> Decimal:
        """Renta líquida ordinaria de la cédula general = 91 − 92."""
        return _no_negativo(self.casilla_91 - self.casilla_92)

    @property
    def casilla_97(self) -> Decimal:
        """Renta líquida gravable de la cédula general = 93 + 96 − 94 − 95."""
        return _no_negativo(
            self.casilla_93
            + self.rentas_gravables
            - self.compensacion_2018_y_anteriores
            - self.compensacion_exceso_presuntiva
        )


def _imputar_automaticamente(
    columnas: Dict[str, Columna], valor: Decimal
) -> List[Tuple[Columna, Decimal]]:
    """Reparte un concepto sin subcédula asignada entre las columnas con renta.

    Va en el orden del formulario —trabajo, trabajo sin vínculo, capital, no
    laborales— y llena cada columna hasta el espacio que le queda, que es su
    renta líquida menos lo que ya tiene solicitado. Es el mismo orden en que el
    servicio de la DIAN reparte el cupo del art. 336 num. 3, así que el
    resultado coincide con el que vería el contribuyente al diligenciar.

    Si no queda espacio en ninguna columna, el remanente se imputa a la última
    con renta líquida para que aparezca en el borrador y el contador vea que lo
    solicitó: dejarlo fuera lo haría desaparecer sin rastro.
    """
    reparto: List[Tuple[Columna, Decimal]] = []
    restante = valor
    con_renta = [columnas[s] for s in SUBCEDULAS if columnas[s].renta_liquida > CERO]
    for columna in con_renta:
        if restante <= CERO:
            break
        espacio = _no_negativo(columna.renta_liquida - columna.solicitado)
        parte = min(restante, espacio)
        if parte > CERO:
            reparto.append((columna, parte))
            restante -= parte
    if restante > CERO:
        destino = con_renta[-1] if con_renta else columnas[TRABAJO]
        reparto.append((destino, restante))
    return reparto


def _repartir_en_cascada(
    columnas: Dict[str, Columna], aceptado: Decimal
) -> List[str]:
    """Reparte el monto aceptado entre las columnas, en el orden del formulario.

    El instructivo del 210 es explícito y no deja margen: «se distribuirá en
    las casillas correspondientes (…) de la siguiente manera: primero a las
    Rentas de trabajo, segundo a las Rentas de trabajo que no provengan de una
    relación laboral o legal y reglamentaria, después a las Rentas de capital y
    por último a las Rentas no laborales, hasta agotar el valor total».

    Es una cascada, no un reparto a prorrata: la primera columna toma todo lo
    que puede y las siguientes reciben el saldo. Repartir proporcionalmente da
    el mismo impuesto total pero casillas distintas a las que calcula el
    servicio de diligenciamiento de la DIAN, y el contribuyente que transcriba
    el borrador vería su declaración corregida.

    Cada columna tiene además dos techos propios, también del instructivo: lo
    que efectivamente solicitó, y su propia renta líquida más las rentas
    pasivas ECE. El segundo techo es el que evita que una columna quede en
    negativo; cuando muerde, el beneficio se pierde y hay que decirlo.
    """
    diagnosticos: List[str] = []
    saldo = aceptado
    for subcedula in SUBCEDULAS:
        columna = columnas[subcedula]
        if saldo <= CERO:
            columna.limitadas = CERO
            continue
        techo_renta = columna.renta_liquida + columna.rentas_pasivas_ece
        asignado = min(saldo, columna.solicitado, techo_renta)
        columna.limitadas = asignado
        saldo -= asignado
        if columna.solicitado > techo_renta and min(saldo + asignado, columna.solicitado) > techo_renta:
            diagnosticos.append(
                f"En {_NOMBRE_COLUMNA[subcedula]} las rentas exentas y deducciones "
                f"solicitadas (${columna.solicitado.quantize(_CENTAVO)}) superan la "
                f"renta líquida de esa misma columna "
                f"(${techo_renta.quantize(_CENTAVO)}): el formulario no permite "
                f"imputar más de la renta líquida de la columna, así que "
                f"${(columna.solicitado - techo_renta).quantize(_CENTAVO)} no se "
                f"restan en ninguna parte. Revise si esas deducciones corresponden "
                f"realmente a esta subcédula."
            )
    return diagnosticos


def depurar(
    trabajo,
    capital,
    no_laborales,
    conceptos,
    exenta_25_por_ciento: Decimal,
    dependientes: Decimal,
    compras_1_por_ciento: Decimal,
    rentas_gravables: Decimal,
    parametros: ParametrosAnuales,
) -> ResultadoCedulaGeneral:
    """Arma la grilla de la cédula general y aplica el límite del art. 336."""
    columnas = {s: Columna(subcedula=s) for s in SUBCEDULAS}

    # --- Rentas de trabajo -------------------------------------------------
    # Los honorarios van a su propia columna solo si se optó por restar costos
    # y gastos (art. 336 num. 4); si no, acompañan al salario.
    col_trabajo = columnas[TRABAJO]
    col_trabajo.ingresos_brutos = trabajo.ingresos_brutos
    col_trabajo.ingresos_no_constitutivos = trabajo.total_incrngo
    if trabajo.opta_por_costos_y_gastos:
        col_sin_vinculo = columnas[SIN_VINCULO]
        col_sin_vinculo.ingresos_brutos = trabajo.ingresos_sin_vinculo_laboral
        col_sin_vinculo.costos_y_deducciones = trabajo.costos_y_gastos_sin_vinculo_laboral
    else:
        col_trabajo.ingresos_brutos += trabajo.ingresos_sin_vinculo_laboral

    # --- Rentas de capital y no laborales ----------------------------------
    columnas[CAPITAL].ingresos_brutos = capital.ingresos_brutos
    columnas[CAPITAL].ingresos_no_constitutivos = capital.ingresos_no_constitutivos
    columnas[CAPITAL].costos_y_deducciones = capital.total_costos
    columnas[NO_LABORAL].ingresos_brutos = no_laborales.ingresos_brutos
    columnas[NO_LABORAL].devoluciones = getattr(no_laborales, "devoluciones", CERO)
    columnas[NO_LABORAL].ingresos_no_constitutivos = no_laborales.ingresos_no_constitutivos
    columnas[NO_LABORAL].costos_y_deducciones = no_laborales.total_costos

    resultado = ResultadoCedulaGeneral(columnas=columnas)

    # --- Conceptos imputados a su columna y a su fila ----------------------
    #
    # Si el contador fijó la subcédula, se respeta: él sabe de dónde salió el
    # gasto. Si no la fijó, hay que imputarla, y no sirve mandarla toda a
    # rentas de trabajo: el formulario no permite que una columna reste más que
    # su propia renta líquida, así que una deducción imputada a una columna sin
    # ingresos se perdería completa y el contribuyente pagaría impuesto sobre
    # una base que la ley no le exige. Se reparte entonces en el orden del
    # formulario, llenando cada columna hasta su renta líquida.
    for concepto in conceptos:
        if concepto.subcedula:
            destinos = [(columnas[concepto.subcedula], concepto.valor)]
        else:
            destinos = _imputar_automaticamente(columnas, concepto.valor)
        for destino, parte in destinos:
            if parte <= CERO:
                continue
            if not concepto.sujeto_a_limite_general:
                destino.sin_limite += parte
            if concepto.tipo == EXENTA_AFC:
                destino.exenta_afc += parte
            elif concepto.tipo == DEDUCCION_VIVIENDA:
                destino.deduccion_vivienda += parte
            elif concepto.tipo == DEDUCCION_OTRA:
                destino.deduccion_otra += parte
            else:
                destino.exenta_otra += parte

    # La renta exenta del 25 % es de las rentas de trabajo por definición.
    col_trabajo.exenta_otra += exenta_25_por_ciento

    # --- Límite del art. 336 num. 3 ----------------------------------------
    #
    # La base del 40 % es la suma de los ingresos brutos de las cuatro columnas
    # más las rentas pasivas ECE, menos los ingresos no constitutivos. Las
    # devoluciones de la casilla 75 NO se restan de esta base: el instructivo
    # enumera lo que se suma y dice «y se restan los ingresos no
    # constitutivos», sin mencionarlas. Restarlas daría un límite más bajo y un
    # impuesto más alto que el que calcula la DIAN.
    ingresos_cg = sum(
        (c.ingresos_brutos + c.rentas_pasivas_ece for c in columnas.values()), CERO
    )
    incrngo_cg = sum((c.ingresos_no_constitutivos for c in columnas.values()), CERO)
    resultado.base_del_limite = _no_negativo(ingresos_cg - incrngo_cg)

    limite = parametros.limite_general
    solicitado_limitable = sum(
        (c.solicitado_limitable for c in columnas.values()), CERO
    )
    porcentual = resultado.base_del_limite * (limite.porcentaje or CERO)
    tope = (limite.tope_uvt or CERO) * parametros.uvt
    aceptado_limitable = min(solicitado_limitable, porcentual, tope)

    # Las rentas exentas que la ley dejó fuera del límite (art. 206 nums. 6 a 9,
    # art. 206-1, art. 207-2 nums. 3 y 4, convenios de doble tributación y
    # Decisión 578 de la CAN) se suman ENCIMA del 40 %: no compiten por el
    # mismo cupo. Van en la fila de rentas exentas de su columna, no en una
    # deducción aparte.
    aceptado = aceptado_limitable + sum(
        (c.sin_limite for c in columnas.values()), CERO
    )

    diag_cascada = _repartir_en_cascada(columnas, aceptado)
    resultado.diagnosticos.extend(diag_cascada)
    resultado.limitadas_total = sum((c.limitadas for c in columnas.values()), CERO)

    if aceptado_limitable < solicitado_limitable:
        cual = (
            f"el {porcentaje_legible(limite.porcentaje)} % de los ingresos depurados"
            if porcentual <= tope
            else f"el tope de {limite.tope_uvt} UVT"
        )
        resultado.diagnosticos.append(
            f"El límite del art. 336 num. 3 recortó "
            f"${(solicitado_limitable - aceptado_limitable).quantize(_CENTAVO)} de las "
            f"rentas exentas y deducciones solicitadas: se aceptaron "
            f"${aceptado_limitable.quantize(_CENTAVO)} de "
            f"${solicitado_limitable.quantize(_CENTAVO)} porque {cual} es la cifra "
            f"menor. El exceso no se traslada a otros años ni a otras cédulas."
        )

    # --- Casilla 139: adición por dependientes -----------------------------
    #
    # Topada en la suma de las casillas 42 y 57, es decir en la renta líquida
    # ordinaria de las dos columnas de rentas de trabajo. Sin este techo, un
    # contribuyente con dependientes y poca renta de trabajo restaría más de lo
    # que tiene.
    techo_dependientes = (
        columnas[TRABAJO].renta_liquida_ordinaria
        + columnas[SIN_VINCULO].renta_liquida_ordinaria
    )
    resultado.deduccion_dependientes = min(dependientes, techo_dependientes)
    if dependientes > resultado.deduccion_dependientes:
        resultado.diagnosticos.append(
            f"La adición por dependientes de la casilla 139 se limitó a "
            f"${resultado.deduccion_dependientes.quantize(_CENTAVO)}: el instructivo "
            f"no permite que exceda la renta líquida ordinaria de las rentas de "
            f"trabajo (casillas 42 y 57). Se solicitaron "
            f"${dependientes.quantize(_CENTAVO)}."
        )

    # --- Casilla 28: 1 % de compras con factura electrónica ----------------
    #
    # No está sujeta al límite del num. 3, pero «no podrá dar lugar a pérdidas»:
    # se topa en lo que quede de renta líquida ordinaria después de los
    # dependientes.
    ordinarias = sum((c.renta_liquida_ordinaria for c in columnas.values()), CERO)
    techo_compras = _no_negativo(ordinarias - resultado.deduccion_dependientes)
    resultado.deduccion_compras = min(compras_1_por_ciento, techo_compras)
    if compras_1_por_ciento > resultado.deduccion_compras:
        resultado.diagnosticos.append(
            f"La deducción del 1 % de compras con factura electrónica se limitó a "
            f"${resultado.deduccion_compras.quantize(_CENTAVO)}: el art. 336 num. 5 "
            f"no la sujeta al límite del 40 %, pero no puede dar lugar a pérdidas. Se "
            f"solicitaron ${compras_1_por_ciento.quantize(_CENTAVO)}."
        )

    resultado.rentas_gravables = rentas_gravables
    return resultado


def casillas_de(resultado: ResultadoCedulaGeneral) -> List[Tuple[int, str, Decimal]]:
    """Las celdas de la grilla con valor, como (casilla, nombre de la fila, valor).

    Solo se devuelven las celdas con valor distinto de cero: un formulario con
    cien ceros impresos es ilegible, y las casillas vacías se dejan vacías.
    """
    filas = [
        ("Ingresos brutos", lambda c: c.ingresos_brutos),
        ("Devoluciones, rebajas y descuentos", lambda c: c.devoluciones),
        ("Ingresos no constitutivos de renta", lambda c: c.ingresos_no_constitutivos),
        ("Costos y deducciones procedentes", lambda c: c.costos_y_deducciones),
        ("Renta líquida", lambda c: c.renta_liquida),
        ("Rentas líquidas pasivas — ECE", lambda c: c.rentas_pasivas_ece),
        ("Rentas exentas — aportes voluntarios AFC, FVP y AVC", lambda c: c.exenta_afc),
        ("Rentas exentas — otras rentas exentas", lambda c: c.exenta_otra),
        ("Total rentas exentas", lambda c: c.total_rentas_exentas),
        ("Deducciones imputables — intereses de vivienda", lambda c: c.deduccion_vivienda),
        ("Deducciones imputables — otras deducciones imputables", lambda c: c.deduccion_otra),
        ("Total deducciones imputables", lambda c: c.total_deducciones),
        ("Rentas exentas y/o deducciones imputables (limitadas)", lambda c: c.limitadas),
        ("Renta líquida ordinaria del ejercicio", lambda c: c.renta_liquida_ordinaria_ejercicio),
        ("Pérdida líquida del ejercicio", lambda c: c.perdida_liquida),
        ("Compensaciones por pérdidas", lambda c: c.compensaciones),
        ("Renta líquida ordinaria", lambda c: c.renta_liquida_ordinaria),
    ]
    salida: List[Tuple[int, str, Decimal]] = []
    for nombre, obtener in filas:
        for subcedula in SUBCEDULAS:
            casilla = casilla_de_subcedula(nombre, subcedula)
            if casilla is None:
                continue
            valor = obtener(resultado.columnas[subcedula])
            if valor != CERO:
                salida.append((casilla, nombre, valor))
    return sorted(salida)
