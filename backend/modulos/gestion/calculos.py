"""Cálculos de gestión: firmeza, beneficio de auditoría, corrección, intereses,
comparativo y documentos. Sin base de datos ni reloj.
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.formato import pesos

CERO = Decimal("0")
_PESO = Decimal("1")


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(_PESO, rounding=ROUND_HALF_UP)


def sumar_meses(fecha: date, meses: int) -> date:
    """Suma N meses; si el día no existe, último día del mes."""
    total = fecha.month - 1 + meses
    anio, mes = fecha.year + total // 12, total % 12 + 1
    return date(anio, mes, min(fecha.day, calendar.monthrange(anio, mes)[1]))


# Firmeza (art. 714 ET)


@dataclass
class Firmeza:
    fecha: Optional[date]
    regla: str
    fuente: str
    desde: Optional[date] = None
    notas: List[str] = field(default_factory=list)


def calcular_firmeza(
    vencimiento: Optional[date],
    presentacion: Optional[date],
    tiene_saldo_a_favor: bool = False,
    solicitud_devolucion: Optional[date] = None,
    liquida_o_compensa_perdidas: bool = False,
    meses_beneficio_auditoria: Optional[int] = None,
) -> Firmeza:
    """Fecha de firmeza (art. 714).

    - General: 3 años desde el vencimiento.
    - Extemporánea: 3 años desde la presentación.
    - Saldo a favor solicitado: 3 años desde la solicitud.
    - Liquida o compensa pérdidas: 5 años.
    - Beneficio de auditoría (art. 689-3): 6 o 12 meses.
    No considera requerimientos especiales notificados.
    """
    fuente = "Art. 714 ET"
    if presentacion is None:
        return Firmeza(None, "La declaración no se ha presentado: la firmeza "
                       "empieza a contar cuando se presente.", fuente)
    if vencimiento is None:
        return Firmeza(None, "Falta la fecha de vencimiento del plazo para "
                       "declarar (calendario de la DIAN o fecha manual).", fuente)

    notas: List[str] = []
    if meses_beneficio_auditoria:
        fecha = sumar_meses(presentacion, meses_beneficio_auditoria)
        notas.append(
            "Es la firmeza del beneficio de auditoría: se pierde si la "
            "declaración no se pagó completa a tiempo o si la DIAN notifica "
            "emplazamiento para corregir dentro de ese plazo; en ese caso "
            "vuelve la regla general del art. 714."
        )
        if liquida_o_compensa_perdidas:
            notas.append(
                "Con pérdidas fiscales, la DIAN conserva la facultad de revisar "
                "su procedencia aunque haya beneficio de auditoría (art. 689-3 ET)."
            )
        return Firmeza(
            fecha,
            f"{meses_beneficio_auditoria} meses desde la presentación por "
            f"beneficio de auditoría",
            "Art. 689-3 ET, prorrogado por el art. 69 de la Ley 2294 de 2023",
            presentacion,
            notas,
        )

    if tiene_saldo_a_favor and solicitud_devolucion:
        desde, motivo = solicitud_devolucion, "la solicitud de devolución o compensación"
    elif presentacion > vencimiento:
        desde, motivo = presentacion, "la presentación (se presentó tarde)"
    else:
        desde, motivo = vencimiento, "el vencimiento del plazo para declarar"
    if tiene_saldo_a_favor and not solicitud_devolucion:
        notas.append(
            "Tiene saldo a favor: si se pide en devolución o compensación, la "
            "firmeza se cuenta desde esa solicitud y la fecha cambia."
        )

    anios = 5 if liquida_o_compensa_perdidas else 3
    if liquida_o_compensa_perdidas:
        notas.append("Liquida o compensa pérdidas fiscales: el término es de cinco años.")
    fecha = sumar_meses(desde, 12 * anios)
    return Firmeza(fecha, f"{anios} años desde {motivo}", fuente, desde, notas)


# Beneficio de auditoría (art. 689-3 ET)

ANIOS_BENEFICIO = (2024, 2025, 2026)  # Ley 2294 de 2023, art. 69
INCREMENTO_6_MESES = Decimal("0.35")
INCREMENTO_12_MESES = Decimal("0.25")
MINIMO_UVT_ANIO_ANTERIOR = Decimal("71")


@dataclass
class Condicion:
    descripcion: str
    cumple: Optional[bool]  # None = sin datos para saberlo
    detalle: str = ""


@dataclass
class BeneficioAuditoria:
    vigente: bool
    meses: Optional[int]  # 6, 12 o None
    incremento: Optional[Decimal]  # fracción: 0.35 = 35 %
    impuesto_actual: Decimal
    impuesto_anterior: Optional[Decimal]
    impuesto_para_12_meses: Optional[Decimal] = None
    impuesto_para_6_meses: Optional[Decimal] = None
    condiciones: List[Condicion] = field(default_factory=list)
    conclusion: str = ""
    fuente: str = "Art. 689-3 ET, prorrogado por el art. 69 de la Ley 2294 de 2023"


def calcular_beneficio_auditoria(
    anio_gravable: int,
    impuesto_neto_actual: Decimal,
    impuesto_neto_anterior: Optional[Decimal],
    uvt_anio_anterior: Decimal,
    presentada_a_tiempo: Optional[bool],
    pagada_a_tiempo: Optional[bool],
) -> BeneficioAuditoria:
    """Beneficio de auditoría: impuesto neto (casilla 126) +35 % -> 6 meses,
    +25 % -> 12 meses. Año anterior >= 71 UVT; presentar y pagar a tiempo.
    """
    resultado = BeneficioAuditoria(
        vigente=anio_gravable in ANIOS_BENEFICIO,
        meses=None,
        incremento=None,
        impuesto_actual=impuesto_neto_actual,
        impuesto_anterior=impuesto_neto_anterior,
    )
    if not resultado.vigente:
        resultado.conclusion = (
            f"El beneficio de auditoría está prorrogado para los años gravables "
            f"{ANIOS_BENEFICIO[0]} a {ANIOS_BENEFICIO[-1]}; para {anio_gravable} no "
            f"hay norma que lo conceda."
        )
        return resultado
    if impuesto_neto_anterior is None:
        resultado.conclusion = (
            "Falta el impuesto neto de renta del año anterior (casilla 126 de la "
            "declaración anterior). Regístrelo para saber si alcanza el beneficio."
        )
        return resultado

    minimo = MINIMO_UVT_ANIO_ANTERIOR * uvt_anio_anterior
    resultado.condiciones.append(Condicion(
        f"Impuesto neto del año anterior de al menos {MINIMO_UVT_ANIO_ANTERIOR} UVT",
        impuesto_neto_anterior >= minimo,
        f"{pesos(impuesto_neto_anterior)} frente a un mínimo de {pesos(minimo)}",
    ))
    if impuesto_neto_anterior > CERO:
        resultado.incremento = (
            impuesto_neto_actual - impuesto_neto_anterior
        ) / impuesto_neto_anterior
        resultado.impuesto_para_12_meses = _redondear(
            impuesto_neto_anterior * (1 + INCREMENTO_12_MESES))
        resultado.impuesto_para_6_meses = _redondear(
            impuesto_neto_anterior * (1 + INCREMENTO_6_MESES))
    incremento = resultado.incremento or CERO
    alcanza = None
    if incremento >= INCREMENTO_6_MESES:
        alcanza = 6
    elif incremento >= INCREMENTO_12_MESES:
        alcanza = 12
    resultado.condiciones.append(Condicion(
        "Incremento del impuesto neto de renta de al menos 25 % (12 meses) o "
        "35 % (6 meses)",
        alcanza is not None,
        f"Incremento de {str((incremento * 100).quantize(Decimal('0.1'))).replace('.', ',')} %",
    ))
    resultado.condiciones.append(Condicion(
        "Presentada dentro del plazo", presentada_a_tiempo,
        "" if presentada_a_tiempo is not None else "Aún no se ha presentado",
    ))
    resultado.condiciones.append(Condicion(
        "Pagada completa dentro del plazo", pagada_a_tiempo,
        "" if pagada_a_tiempo is not None else "Aún no se ha registrado el pago",
    ))
    resultado.condiciones.append(Condicion(
        "Sin beneficios por ubicación (Zomac, Zese, zonas francas) ni "
        "retenciones inexistentes", None, "Lo confirma el contador",
    ))

    bloqueos = [c for c in resultado.condiciones if c.cumple is False]
    if bloqueos:
        resultado.conclusion = "No alcanza el beneficio de auditoría. No cumple: " + "; ".join(
            c.descripcion[0].lower() + c.descripcion[1:] + (f" ({c.detalle})" if c.detalle else "")
            for c in bloqueos) + "."
        if (
            alcanza is None
            and resultado.impuesto_para_12_meses is not None
            and impuesto_neto_anterior >= minimo
        ):
            resultado.conclusion += (
                f" Con un impuesto neto de renta de "
                f"{pesos(resultado.impuesto_para_12_meses)} quedaría en firme en 12 "
                f"meses, y con {pesos(resultado.impuesto_para_6_meses)}, en 6."
            )
        return resultado

    resultado.meses = alcanza
    pendientes = [c for c in resultado.condiciones if c.cumple is None]
    resultado.conclusion = (
        f"Alcanza el beneficio de auditoría: firmeza en {alcanza} meses desde la "
        f"presentación"
        + (", si se cumplen las condiciones pendientes." if pendientes else ".")
    )
    return resultado


# Corrección (arts. 588, 589, 644 ET)

SANCION_MINIMA_UVT = Decimal("10")
REDUCCIONES_640 = {"NINGUNA": Decimal("1"), "AL_75": Decimal("0.75"), "AL_50": Decimal("0.50")}


@dataclass
class Correccion:
    tipo: str  # AUMENTA | DISMINUYE | SIN_EFECTO
    mayor_valor: Decimal  # positivo: más a pagar o menos saldo a favor
    sancion: Decimal = CERO
    plazo: Optional[date] = None
    vencida: Optional[bool] = None
    formula: str = ""
    fuente: str = ""
    notas: List[str] = field(default_factory=list)


def _neto(saldo_a_pagar: Decimal, saldo_a_favor: Decimal) -> Decimal:
    return saldo_a_pagar - saldo_a_favor


def meses_o_fraccion(desde: date, hasta: date) -> int:
    """Meses o fracción entre dos fechas (mínimo 1)."""
    if hasta <= desde:
        return 0
    meses = (hasta.year - desde.year) * 12 + (hasta.month - desde.month)
    if hasta.day > desde.day:
        meses += 1
    return max(meses, 1)


def calcular_correccion(
    saldo_a_pagar_anterior: Decimal,
    saldo_a_favor_anterior: Decimal,
    saldo_a_pagar_nuevo: Decimal,
    saldo_a_favor_nuevo: Decimal,
    vencimiento: Optional[date],
    presentacion_inicial: Optional[date],
    fecha_correccion: date,
    uvt: Decimal,
    despues_de_emplazamiento: bool = False,
    reduccion: str = "NINGUNA",
) -> Correccion:
    """Sanción y plazo de una corrección.

    Mayor valor: diferencia de (saldo a pagar − saldo a favor) frente a la
    anterior, sin la propia sanción (art. 644 par. 3).
    """
    mayor_valor = (_neto(saldo_a_pagar_nuevo, saldo_a_favor_nuevo)
                   - _neto(saldo_a_pagar_anterior, saldo_a_favor_anterior))

    if mayor_valor < CERO:
        plazo = sumar_meses(vencimiento, 12) if vencimiento else None
        return Correccion(
            "DISMINUYE", mayor_valor, CERO, plazo,
            (fecha_correccion > plazo) if plazo else None,
            "Disminuye el valor a pagar o aumenta el saldo a favor: no lleva sanción.",
            "Art. 589 ET",
            ["Se tramita con el procedimiento del art. 589, dentro del año "
             "siguiente al vencimiento del plazo para declarar."],
        )

    plazo = sumar_meses(vencimiento, 36) if vencimiento else None
    vencida = (fecha_correccion > plazo) if plazo else None
    notas = ["Solo procede antes de que la DIAN notifique requerimiento especial "
             "o pliego de cargos (art. 588 ET)."]
    if mayor_valor == CERO:
        return Correccion("SIN_EFECTO", CERO, CERO, plazo, vencida,
                          "No cambia el valor a pagar ni el saldo a favor: no "
                          "lleva sanción.", "Art. 588 ET", notas)

    tarifa = Decimal("0.20") if despues_de_emplazamiento else Decimal("0.10")
    sancion = mayor_valor * tarifa
    formula = (f"{int(tarifa * 100)} % × mayor valor {pesos(mayor_valor)}"
               + (" (después del emplazamiento para corregir)"
                  if despues_de_emplazamiento else ""))
    if (vencimiento and presentacion_inicial
            and presentacion_inicial > vencimiento):
        meses = meses_o_fraccion(vencimiento, presentacion_inicial)
        adicional = mayor_valor * Decimal("0.05") * meses
        sancion += adicional
        formula += (f" + 5 % × {meses} mes(es) de extemporaneidad de la "
                    f"declaración inicial")
        sancion = min(sancion, mayor_valor)
        formula += ", sin exceder el 100 % del mayor valor"
    factor = REDUCCIONES_640.get(reduccion, Decimal("1"))
    if factor != 1:
        sancion *= factor
        formula += f"; reducida al {int(factor * 100)} % (art. 640 ET)"
    minima = SANCION_MINIMA_UVT * uvt
    if sancion < minima:
        sancion = minima
        formula += f"; se eleva a la sanción mínima de 10 UVT ({pesos(minima)})"
    notas.append("Los mayores valores generan además intereses de mora desde el "
                 "vencimiento original (art. 644 par. 2).")
    return Correccion("AUMENTA", mayor_valor, _redondear(sancion), plazo, vencida,
                      formula, "Arts. 588, 639, 640 y 644 ET", notas)


# Intereses moratorios (arts. 634 y 635 ET)


@dataclass
class TramoInteres:
    desde: date
    hasta: date
    dias: int
    tasa: Decimal  # efectiva anual, en fracción
    interes: Decimal


@dataclass
class Intereses:
    capital: Decimal
    valor: Decimal = CERO
    dias: int = 0
    tramos: List[TramoInteres] = field(default_factory=list)
    meses_sin_tasa: List[Tuple[int, int]] = field(default_factory=list)
    formula: str = ("Interés simple diario: capital × tasa del mes ÷ días del año "
                    "× días de mora, mes a mes, desde el día siguiente al "
                    "vencimiento hasta el día del pago")
    fuente: str = "Arts. 634 y 635 ET"


def calcular_intereses(
    capital: Decimal,
    vencimiento: date,
    fecha_pago: date,
    tasas: Dict[Tuple[int, int], Decimal],
) -> Intereses:
    """Intereses de mora: capital × tasa del mes / días del año × días, por mes.

    Mes sin tasa: no se calcula y se reporta.
    """
    resultado = Intereses(capital=capital)
    if capital <= CERO or fecha_pago <= vencimiento:
        return resultado
    dia = vencimiento + timedelta(days=1)
    while dia <= fecha_pago:
        fin_de_mes = date(dia.year, dia.month,
                          calendar.monthrange(dia.year, dia.month)[1])
        hasta = min(fin_de_mes, fecha_pago)
        dias = (hasta - dia).days + 1
        resultado.dias += dias
        tasa = tasas.get((dia.year, dia.month))
        if tasa is None:
            resultado.meses_sin_tasa.append((dia.year, dia.month))
        else:
            dias_anio = 366 if calendar.isleap(dia.year) else 365
            interes = capital * tasa / dias_anio * dias
            resultado.tramos.append(TramoInteres(dia, hasta, dias, tasa, interes))
        dia = hasta + timedelta(days=1)
    resultado.valor = _redondear(sum((t.interes for t in resultado.tramos), CERO))
    for tramo in resultado.tramos:
        tramo.interes = _redondear(tramo.interes)
    return resultado


# Comparación con el año anterior

CASILLAS_COMPARADAS = (29, 30, 31, 32, 43, 58, 74, 91, 93, 97, 99, 107, 108,
                       111, 112, 116, 125, 126, 127, 129, 132, 133, 136, 137)
VARIACION_A_REVISAR = Decimal("0.30")


@dataclass
class FilaComparativo:
    casilla: int
    anterior: Optional[Decimal]
    actual: Optional[Decimal]
    diferencia: Optional[Decimal]
    variacion: Optional[Decimal]
    revisar: bool


@dataclass
class Coherencia:
    descripcion: str
    esperado: Decimal
    registrado: Decimal
    cuadra: bool
    explicacion: str


@dataclass
class Comparativo:
    filas: List[FilaComparativo]
    coherencias: List[Coherencia]


def comparar_con_anterior(
    actual: Dict[int, Decimal],
    anterior: Dict[int, Decimal],
    umbral_minimo: Decimal,
    anterior_incompleto: bool = False,
) -> Comparativo:
    """Comparativo casilla por casilla y dos coherencias.

    Marca variaciones > 30 % sobre un monto mínimo. Con anterior_incompleto, una
    casilla ausente no se marca. Coherencias: 130 = 133 anterior; 131 = 137 anterior.
    """
    filas: List[FilaComparativo] = []
    for n in CASILLAS_COMPARADAS:
        a, b = anterior.get(n), actual.get(n)
        if a is None and b is None:
            continue
        a0, b0 = a or CERO, b or CERO
        diferencia = b0 - a0
        variacion = (diferencia / a0) if a0 != CERO else None
        revisar = abs(diferencia) >= umbral_minimo and (
            variacion is None or abs(variacion) >= VARIACION_A_REVISAR)
        if a is None and anterior_incompleto:
            diferencia, revisar = None, False
        filas.append(FilaComparativo(n, a, b, diferencia, variacion, revisar))

    coherencias: List[Coherencia] = []
    if 133 in anterior:
        esperado, registrado = anterior[133], actual.get(130, CERO)
        coherencias.append(Coherencia(
            "Anticipo del año anterior (casilla 130)", esperado, registrado,
            esperado == registrado,
            "Debe ser el anticipo liquidado en la casilla 133 de la declaración "
            "anterior. Si no coincide, la DIAN lo detecta al cruzar las dos "
            "declaraciones.",
        ))
    if 137 in anterior:
        esperado, registrado = anterior[137], actual.get(131, CERO)
        coherencias.append(Coherencia(
            "Saldo a favor del año anterior (casilla 131)", esperado, registrado,
            esperado == registrado,
            "Debe ser el saldo a favor de la casilla 137 de la declaración "
            "anterior, salvo que se haya pedido en devolución o compensación: en "
            "ese caso va en cero.",
        ))
    return Comparativo(filas, coherencias)


# Documentos para el cliente


@dataclass
class DocumentoSugerido:
    clave: str
    descripcion: str
    tercero: str = ""
    nit: str = ""
    motivo: str = ""


@dataclass
class RegistroParaDocumentos:
    nit: str
    nombre: str
    detalle: str
    concepto: Optional[str]
    info: Optional[str] = None
    es_auto_reportado: bool = False
    es_dian: bool = False


# Un certificado tributario por banco (saldos, deudas, rendimientos, GMF).
_CERT_BANCARIO = ("Certificado tributario anual: saldos y deudas a 31 de diciembre, "
                  "rendimientos, intereses y GMF pagados")

# (patrón sobre concepto + detalle, tipo, descripción). Gana la primera.
_REGLAS: Sequence[Tuple[str, str, str]] = (
    (r"retenci[oó]n", "", ""),  # incluido en el certificado del mismo tercero
    (r"\b(5001|5002)\b|salario|pagos laborales|pensi[oó]n de jubilaci",
     "CERT_220", "Certificado de ingresos y retenciones por rentas de trabajo y "
     "de pensiones (formulario 220)"),
    (r"\b1032\b|notar[ií]a",
     "ESCRITURA", "Escritura pública y documentos de la compraventa registrada "
     "en notaría (costo fiscal y valor de venta)"),
    (r"\b1476\b|aval[uú]o catastral",
     "PREDIAL", "Recibo del impuesto predial y certificado de tradición del inmueble"),
    (r"veh[ií]cul|automotor",
     "VEHICULO", "Impuesto vehicular y tarjeta de propiedad del vehículo"),
    (r"dividend|participaciones",
     "DIVIDENDOS", "Certificado de dividendos y participaciones (gravados y no gravados)"),
    (r"\b1023\b|tarjeta", "BANCARIO", _CERT_BANCARIO),
    (r"cr[eé]dito|pr[eé]stamo|hipotec|leasing",
     "DEUDA", "Certificado del saldo de la deuda a 31 de diciembre y de los "
     "intereses pagados en el año"),
    (r"\b(1110|1020|1301)\b|cuentas? de ahorro|corriente|movimientos en cuentas|\bcdt\b|inversi[oó]n|"
     r"rendimiento|fiducia|fondo",
     "BANCARIO", _CERT_BANCARIO),
    (r"\b(5004|5005|5002|5003)\b|honorario|comisi|servicio|compras|pagos o abonos",
     "CERT_RETENCION", "Certificado de ingresos y retenciones en la fuente "
     "practicadas por el pagador"),
)

_POR_DEDUCCION = {
    "INTERESES_VIVIENDA": "Certificado de intereses pagados por el crédito de vivienda",
    "INTERESES_ICETEX": "Certificado de intereses pagados al ICETEX",
    "MEDICINA_PREPAGADA": "Certificado de pagos por medicina prepagada o seguros de salud",
    "DEPENDIENTES_387": "Soportes de los dependientes (registro civil, certificado "
                        "de estudio o de dependencia económica)",
    "APORTES_VOLUNTARIOS_PENSION": "Certificado de aportes voluntarios a pensión",
    "AHORRO_AFC": "Certificado de aportes a cuentas AFC o AVC",
    "GMF": "Certificado bancario del gravamen a los movimientos financieros pagado",
    "IMPUESTOS_PAGADOS": "Recibos de los impuestos pagados que se deducen",
}


def sugerir_documentos(
    registros: Iterable[RegistroParaDocumentos],
    codigos_deducciones: Iterable[str] = (),
    numero_dependientes: int = 0,
    tiene_declaracion_anterior: bool = False,
    tiene_deudas: bool = False,
) -> List[DocumentoSugerido]:
    """Documentos que soportan la declaración: uno por tercero y tipo.
    No se piden los reportados por la DIAN o el propio contribuyente.
    """
    docs: Dict[str, DocumentoSugerido] = {}

    def agregar(doc: DocumentoSugerido) -> None:
        if doc.clave not in docs:
            docs[doc.clave] = doc
        elif doc.motivo and doc.motivo not in docs[doc.clave].motivo:
            docs[doc.clave].motivo += f"; {doc.motivo}"

    for r in registros:
        if r.es_dian or r.es_auto_reportado:
            continue
        texto = f"{r.concepto or ''} {r.detalle}".lower()
        for patron, tipo, descripcion in _REGLAS:
            if re.search(patron, texto):
                break
        else:
            tipo, descripcion = "OTRO", "Soporte de lo reportado por el tercero"
        if not tipo:
            continue
        motivo = re.sub(r"\s*\(Concepto:\s*\d+\)", "", r.detalle).strip()
        clave = f"{tipo}:{r.nit}"
        if tipo == "PREDIAL" and r.info:
            matricula = re.search(r"Matr[ií]cula:\s*([\w-]+)", r.info)
            if matricula:
                clave = f"PREDIAL:{matricula.group(1)}"
                descripcion += f" (matrícula {matricula.group(1)})"
        agregar(DocumentoSugerido(clave, descripcion, r.nombre, r.nit,
                                  f"La exógena reporta: {motivo}"))

    for codigo in codigos_deducciones:
        if codigo in _POR_DEDUCCION:
            agregar(DocumentoSugerido(
                f"DEDUCCION:{codigo}", _POR_DEDUCCION[codigo],
                motivo="Soporta una deducción o renta exenta solicitada"))
    if numero_dependientes > 0:
        agregar(DocumentoSugerido(
            "DEPENDIENTES", _POR_DEDUCCION["DEPENDIENTES_387"],
            motivo=f"Se declaran {numero_dependientes} dependiente(s)"))
    if tiene_deudas:
        agregar(DocumentoSugerido(
            "DEUDAS", "Certificados del saldo de todas las deudas a 31 de diciembre",
            motivo="Las deudas restan del patrimonio y la DIAN pide su soporte"))
    if not tiene_declaracion_anterior:
        agregar(DocumentoSugerido(
            "DECLARACION_ANTERIOR", "Copia de la declaración de renta del año anterior",
            motivo="Para el anticipo, el saldo a favor, el patrimonio anterior y "
                   "el beneficio de auditoría"))
    return list(docs.values())
