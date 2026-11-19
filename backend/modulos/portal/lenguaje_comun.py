"""Traducción de una fila de la exógena a una petición en lenguaje común.

El problema
-----------
Una fila de la exógena dice:

    900111222 | BANCO EJEMPLO S A | Saldo de cuentas de ahorro y corrientes a
    31 de diciembre (Concepto: 1110) | 14.850.000

Eso es legible para un contador y no para el contribuyente, que es quien tiene
el documento. Pedirle «el soporte del concepto 1110» garantiza que conteste
«¿cuál?» o que mande cualquier cosa. Pedirle «el extracto de diciembre de su
cuenta del Banco Ejemplo» lo resuelve sin explicaciones.

De ahí las dos reglas de este módulo:

1. **El título se arma con el nombre del tercero, no con el concepto
   tributario.** El contribuyente reconoce «Bancolombia»; no reconoce «1110».
2. **Lo que se pide sale del propio `detalle` que escribe la DIAN**, no de una
   tabla de códigos inventada. La DIAN ya describe el concepto en palabras en
   esa columna; usarla es leer el archivo, no adivinar. Los códigos de
   concepto cambian de resolución en resolución y una tabla que afirme
   «1110 = cuentas bancarias» es una fuente de error silencioso.

Qué pasa con lo que no se reconoce
----------------------------------
Nada se descarta. Si ninguna regla aplica, la fila **igual** produce un
requerimiento, con un título genérico y `concepto_reconocido=False`, para que
el contador lo clasifique a mano. Descartar una fila de la exógena es
exactamente el error que la aplicación existe para evitar: lo que no aparece
en la conciliación es lo que después aparece en un requerimiento de la DIAN.

Cuando la regla que aplicó es genérica (coincidió por una palabra suelta como
«impuesto»), la petición se emite igual pero con `motivo_revision`: sirve para
pedir el documento, y el contador sabe que la clasificación es una deducción
de la aplicación y no un dato del archivo.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional

# Categoría de adjunto sugerida. Son los valores de
# `modulos.adjuntos.modelos.CategoriaAdjunto`; se escriben como texto para no
# acoplar este módulo (puro, sin base de datos) al de adjuntos.
CERTIFICADO = "CERTIFICADO"
RECIBO = "RECIBO"
FACTURA = "FACTURA"
CONTRATO = "CONTRATO"
DECLARACION = "DECLARACION"
OTRO = "OTRO"


@dataclass(frozen=True)
class Regla:
    """Una forma de pedir el documento, con las palabras que la disparan."""

    palabras: tuple
    documento: str
    explicacion: str
    categoria: str
    # False cuando la coincidencia es por una palabra suelta y no por una
    # descripción completa: el documento pedido sirve, pero la clasificación
    # es una deducción y el contador debe confirmarla.
    especifica: bool = True


@dataclass(frozen=True)
class Peticion:
    titulo: str
    explicacion: str
    categoria_sugerida: str
    concepto_reconocido: bool
    # None cuando no hay nada que revisar.
    motivo_revision: Optional[str]
    # False para las filas que son información de la DIAN o de la declaración
    # anterior del propio contribuyente: no existe un tercero a quien pedirle
    # un certificado, así que no se le cobran como pendientes.
    requiere_soporte: bool


_MOTIVO_SIN_RECONOCER = (
    "La aplicación no pudo deducir qué documento respalda este valor. "
    "Clasifíquelo usted antes de usarlo: la fila se conserva tal como vino "
    "del archivo."
)

_MOTIVO_GENERICO = (
    "El documento se dedujo de una palabra del detalle, no de una descripción "
    "completa. Confirme que es el soporte correcto."
)


# El orden importa: gana la primera regla que coincida, así que las
# descripciones más específicas van antes que las palabras sueltas.
# «Retención practicada enajenación en Notaría» tiene que resolverse como
# retención y no como venta de inmueble.
REGLAS: List[Regla] = [
    Regla(
        ("retencion",),
        "Certificado de retención en la fuente",
        "Es el papel donde quien le pagó certifica cuánto le descontó de "
        "impuesto durante el año.",
        CERTIFICADO,
    ),
    Regla(
        ("tarjeta credito", "tarjeta debito", "tarjeta cr", "consumos o gastos con tarjeta"),
        "Extracto de la tarjeta",
        "Sirve el extracto del año o el resumen anual que manda el banco.",
        CERTIFICADO,
    ),
    Regla(
        ("salario", "nomina", "laboral"),
        "Certificado de ingresos y retenciones",
        "Se lo entrega su empleador. Suele llamarse «certificado de ingresos "
        "y retenciones» o «formulario 220».",
        CERTIFICADO,
    ),
    Regla(
        ("honorario", "servicios prestados", "comision", "servicio"),
        "Certificado de ingresos y retenciones",
        "Lo expide la empresa a la que le prestó el servicio, por el total "
        "del año.",
        CERTIFICADO,
    ),
    Regla(
        ("movimientos en cuentas", "consignacion", "deposito"),
        "Extractos del año de la cuenta",
        "Son los extractos mensuales, o el certificado de movimientos que el "
        "banco expide para la declaración.",
        CERTIFICADO,
    ),
    Regla(
        ("saldo de cuentas", "cuenta de ahorro", "cuentas de ahorro", "cuenta corriente"),
        "Extracto de diciembre de la cuenta",
        "Se necesita el saldo al 31 de diciembre. Sirve el extracto de "
        "diciembre o el certificado tributario del banco.",
        CERTIFICADO,
    ),
    Regla(
        ("cdt", "inversion", "fondo de inversion", "titulo"),
        "Certificado del CDT o de la inversión",
        "El banco o la comisionista lo expide una vez al año para la "
        "declaración de renta.",
        CERTIFICADO,
    ),
    Regla(
        ("rendimiento", "interes"),
        "Certificado de intereses o rendimientos",
        "Es el certificado tributario anual que expide el banco.",
        CERTIFICADO,
    ),
    Regla(
        ("arrendamiento", "arriendo", "canon"),
        "Contrato o certificado de arrendamiento",
        "Sirve el contrato vigente, o el certificado de lo pagado o recibido "
        "en el año.",
        CONTRATO,
    ),
    Regla(
        ("avaluo catastral", "predial", "catastral"),
        "Recibo del impuesto predial",
        "El del año que se está declarando: ahí figura el avalúo catastral "
        "del inmueble.",
        RECIBO,
    ),
    Regla(
        ("notaria", "enajenacion", "venta de bienes", "escritura"),
        "Escritura o certificado de la venta",
        "La escritura de la venta, o el certificado que expide la notaría.",
        CONTRATO,
    ),
    Regla(
        ("factura", "compras de bienes", "compra"),
        "Facturas o certificado de compras",
        "Sirve el resumen anual de facturas, o las facturas de los valores "
        "más grandes.",
        FACTURA,
    ),
    Regla(
        ("aporte", "pension", "salud", "seguridad social"),
        "Certificado de aportes",
        "Lo expide el fondo o la EPS, con el total aportado en el año.",
        CERTIFICADO,
    ),
    Regla(
        ("prestamo", "credito", "obligacion financiera", "pasivo", "deuda", "hipotec"),
        "Certificado de saldo del crédito",
        "Es el certificado que el banco expide para la declaración, con el "
        "saldo a 31 de diciembre y los intereses pagados en el año.",
        CERTIFICADO,
    ),
    Regla(
        ("dividendo", "participacion en sociedad", "utilidad"),
        "Certificado de dividendos",
        "Lo expide la sociedad que repartió las utilidades.",
        CERTIFICADO,
    ),
    Regla(
        ("vehiculo", "automotor", "moto"),
        "Recibo del impuesto de vehículos o la tarjeta de propiedad",
        "Sirve el recibo del impuesto del año, o la tarjeta de propiedad.",
        RECIBO,
    ),
    # A partir de aquí, coincidencias por palabra suelta: piden un documento
    # razonable pero la clasificación la confirma el contador.
    Regla(
        ("impuesto", "gravamen", "tasa"),
        "Recibo de pago del impuesto",
        "Sirve el recibo o el certificado de pago del año.",
        RECIBO,
        especifica=False,
    ),
    Regla(
        ("ingreso",),
        "Certificado del ingreso",
        "Un certificado de quien le hizo el pago, con el total del año.",
        CERTIFICADO,
        especifica=False,
    ),
]


# Filas que no son una petición a un tercero sino información que ya está en
# poder del contador: lo que la propia DIAN consolida y lo que viene de la
# declaración del año anterior del contribuyente.
_SOLO_INFORMATIVAS = (
    "patrimonio bruto declarado en el año anterior",
    "saldo a favor",
    "declarado en el año anterior",
)


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


_CONECTORES = {"de", "del", "la", "las", "los", "y", "e", "en", "el", "al", "por"}
_SIGLAS = {"s", "a", "sa", "sas", "ltda", "eu", "sa s", "bic", "esp", "eps", "ips", "uae"}


def nombre_legible(nombre: str) -> str:
    """«BANCOLOMBIA S A» → «Bancolombia S A».

    Los nombres llegan en mayúscula sostenida desde el archivo de la DIAN.
    Mostrarlos así en un mensaje dirigido al contribuyente se lee como un
    grito, pero pasarlos por `title()` convierte las siglas en «S.a.s» y los
    conectores en «De La». Esto respeta las dos cosas.
    """
    palabras = (nombre or "").split()
    if not palabras:
        return "el tercero que lo reportó"
    salida = []
    for i, palabra in enumerate(palabras):
        limpia = _sin_tildes(palabra).strip(".,")
        # «U.A.E.» llega con puntos: sin quitarlos para comparar, `capitalize`
        # la convierte en «U.a.e.».
        nucleo = limpia.replace(".", "")
        if nucleo in _CONECTORES:
            # Los conectores van antes que la regla de siglas: «DEL» y «Y»
            # también son cortos, y «Arrendamientos LA Colina» se lee peor
            # que el original.
            salida.append(palabra.lower() if i > 0 else palabra.capitalize())
        elif nucleo in _SIGLAS or ("." in limpia and len(nucleo) <= 4):
            # La sigla se reconoce por la lista o por venir con puntos. No por
            # ser corta: «LUZ MARINA» es un nombre, no unas iniciales.
            salida.append(palabra.upper())
        else:
            salida.append(palabra.capitalize())
    return " ".join(salida)


def _quitar_concepto(detalle: str) -> str:
    """Saca el «(Concepto: 1110)» y los paréntesis técnicos del detalle."""
    sin_concepto = re.sub(r"\((?:concepto|tipo)[^)]*\)", "", detalle, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", sin_concepto).strip(" .,")


def _buscar_regla(detalle_normalizado: str) -> Optional[Regla]:
    for regla in REGLAS:
        if any(palabra in detalle_normalizado for palabra in regla.palabras):
            return regla
    return None


def traducir(
    detalle: str,
    nombre_reportante: str,
    es_auto_reportado: bool = False,
    es_dian: bool = False,
) -> Peticion:
    """Convierte una fila de la exógena en una petición de documento."""
    detalle = detalle or ""
    normalizado = _sin_tildes(detalle)
    quien = nombre_legible(nombre_reportante)
    resumen = _quitar_concepto(detalle)

    informativa = (
        es_dian
        or es_auto_reportado
        or any(frase in _sin_tildes(detalle) for frase in map(_sin_tildes, _SOLO_INFORMATIVAS))
    )

    regla = _buscar_regla(normalizado)

    # Las filas informativas se resuelven primero. Que no se reconozca el
    # documento de una fila que NO pide documento no es un concepto sin
    # clasificar: ya está clasificado, como información. Marcarlo igual
    # llenaría el panel del contador de alarmas que no son nada, y una alarma
    # que siempre suena es una alarma que se deja de mirar.
    if informativa:
        return Peticion(
            titulo=(
                f"{regla.documento} — {quien}"
                if regla is not None
                else f"Información reportada por {quien}"
            ),
            explicacion=(
                "Este valor no lo reportó un tercero: lo trae la propia DIAN o "
                "su declaración del año anterior. No tiene que cargar nada; "
                f"aparece aquí para que quede a la vista. Detalle: «{resumen}»."
            ),
            categoria_sugerida=DECLARACION,
            concepto_reconocido=True,
            motivo_revision=(
                _MOTIVO_GENERICO if regla is not None and not regla.especifica else None
            ),
            requiere_soporte=False,
        )

    if regla is None:
        return Peticion(
            titulo=f"Soporte de {quien}",
            explicacion=(
                f"El archivo de la DIAN lo describe así: «{resumen}». Si tiene "
                "a mano el papel que respalda este valor, cárguelo; si no "
                "sabe cuál es, marque «No entiendo» y su contador se encarga."
            ),
            categoria_sugerida=OTRO,
            concepto_reconocido=False,
            motivo_revision=_MOTIVO_SIN_RECONOCER,
            requiere_soporte=True,
        )

    return Peticion(
        titulo=f"{regla.documento} de {quien}",
        explicacion=f"{regla.explicacion} En el archivo de la DIAN figura como «{resumen}».",
        categoria_sugerida=regla.categoria,
        concepto_reconocido=True,
        motivo_revision=None if regla.especifica else _MOTIVO_GENERICO,
        requiere_soporte=True,
    )
