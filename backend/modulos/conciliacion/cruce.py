"""El cruce de la declaración contra lo que la DIAN ya sabe.

La exógena trae dos cosas: el detalle de lo que cada tercero reportó y cinco
«topes» consolidados, que son las cifras con las que la DIAN decide a quién
mirar. Este módulo responde tres preguntas con esos datos:

1. **¿El archivo es coherente consigo mismo?** Cada tope se reconstruye desde
   el detalle. Si no cuadra, el archivo se leyó mal o cambió de formato.
2. **¿Lo que se va a declarar aguanta el cruce?** El patrimonio, los ingresos,
   las retenciones y las ganancias ocasionales de la liquidación se comparan
   con lo que reportaron los terceros. Declarar menos de lo que la DIAN ya
   tiene es lo que origina un requerimiento.
3. **¿Se está dejando plata sobre la mesa?** Retenciones reportadas que no se
   están restando, o compras con factura electrónica que dan derecho a la
   deducción del 1 % y no se registraron.

Son funciones puras: reciben los registros, los topes y las cifras de la
liquidación, y no tocan la base de datos.

Cómo se arma cada tope
----------------------
El archivo marca cada registro con el tope al que pertenece en la columna de
uso sugerido («Tope 4: Consignaciones e inversiones»). Dos reglas no son una
simple suma, y ambas salen del propio archivo:

- El **Tope 2 (patrimonio)** es el mayor entre la suma de lo reportado por
  terceros y el patrimonio bruto declarado el año anterior; el archivo lo dice
  en el registro «Total patrimonio bruto declarado en el año anterior».
- Los bienes con **porcentaje de participación** menor al 100 % cuentan por
  esa fracción. El archivo no lo dice con esas palabras: se dedujo de un
  archivo real en el que sumar los avalúos completos superaba el tope, cosa
  imposible si el tope es el mayor de los dos valores. Si en otro archivo la
  regla no se cumple, el cuadre del tope lo delata.
"""

from core.formato import pesos
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

CERO = Decimal("0")
_PESO = Decimal("1")

# Margen para decir «coincide»: mil pesos, que es la aproximación del art. 577.
TOLERANCIA = Decimal("1000")

ALTA, MEDIA, OPORTUNIDAD, OK, SIN_DATO = "ALTA", "MEDIA", "OPORTUNIDAD", "OK", "SIN_DATO"

_PATRON_TOPE = re.compile(r"^\s*Tope\s+(\d)\s*:", re.IGNORECASE)
_PATRON_PISO = re.compile(r"Tope\s+(\d)\s*-.*toma\s+el\s+mayor", re.IGNORECASE)
_PATRON_PARTICIPACION = re.compile(
    r"Porcentaje\s+de\s+Participaci[oó]n:\s*([\d.,]+)", re.IGNORECASE
)
_PATRON_RENGLON = re.compile(r"\bR(\d+)\b")

NOMBRES_TOPE = {
    1: "Ingresos brutos",
    2: "Patrimonio bruto",
    3: "Consumos con tarjeta de crédito",
    4: "Consignaciones, depósitos e inversiones",
    5: "Compras y consumos",
}


def _d(valor) -> Decimal:
    if valor is None:
        return CERO
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


@dataclass
class Registro:
    """Lo que el cruce necesita de un registro de la exógena."""

    detalle: str
    valor: Decimal
    uso_sugerido: str = ""
    info_adicional: str = ""
    renglones_sugeridos: str = ""
    renglones_son_condicionales: bool = False
    es_auto_reportado: bool = False
    es_dian: bool = False
    nombre_reportante: str = ""

    @property
    def tope(self) -> Optional[int]:
        m = _PATRON_TOPE.match(self.uso_sugerido or "")
        return int(m.group(1)) if m else None

    @property
    def es_flujo_sin_bien(self) -> bool:
        """Un movimiento que no deja nada que declarar como activo o ingreso.

        Consumos con tarjeta (tope 3), compras con factura electrónica (tope 5)
        y movimientos o consignaciones en cuentas (tope 4) son dinero que pasó,
        no un bien: marcarlos como «no declarados» es una alarma falsa. Las
        inversiones del mismo tope 4 —un CDT, un fondo— son distintas: o siguen
        siendo un activo a 31 de diciembre o dejaron un rendimiento, así que sí
        hay algo que buscar en la declaración.
        """
        if self.tope in (3, 5):
            return True
        return self.tope == 4 and "inversi" not in (self.detalle or "").lower()

    @property
    def piso_de_tope(self) -> Optional[int]:
        """El registro que fija el piso de un tope (patrimonio del año anterior)."""
        m = _PATRON_PISO.search(self.uso_sugerido or "")
        return int(m.group(1)) if m else None

    @property
    def participacion(self) -> Decimal:
        m = _PATRON_PARTICIPACION.search(self.info_adicional or "")
        if not m:
            return Decimal("1")
        try:
            porcentaje = Decimal(m.group(1).replace(",", "."))
        except Exception:
            return Decimal("1")
        if porcentaje <= CERO or porcentaje > 100:
            return Decimal("1")
        return porcentaje / Decimal("100")

    @property
    def valor_propio(self) -> Decimal:
        """El valor que le corresponde al contribuyente según su participación."""
        return (self.valor * self.participacion).quantize(Decimal("0.01"))

    def renglones(self) -> List[int]:
        return [int(n) for n in _PATRON_RENGLON.findall(self.renglones_sugeridos or "")]


@dataclass
class DetalleTope:
    detalle: str
    reportante: str
    valor: Decimal
    valor_propio: Decimal
    participacion: Decimal


@dataclass
class CuadreDeTope:
    numero: int
    nombre: str
    etiqueta: str
    valor_tope: Decimal
    suma_detalle: Decimal
    piso: Optional[Decimal]
    valor_esperado: Decimal
    cuadra: bool
    umbral: Optional[Decimal]
    supera_umbral: Optional[bool]
    registros: List[DetalleTope] = field(default_factory=list)
    explicacion: str = ""


@dataclass
class Comparacion:
    clave: str
    titulo: str
    casillas: str
    valor_dian: Optional[Decimal]
    valor_declarado: Decimal
    diferencia: Optional[Decimal]
    severidad: str
    mensaje: str


@dataclass
class ResultadoCruce:
    topes: List[CuadreDeTope]
    comparaciones: List[Comparacion]
    pendientes: List[Registro]
    informativos: List[Registro]
    diagnosticos: List[str] = field(default_factory=list)

    def cuenta(self, severidad: str) -> int:
        return sum(1 for c in self.comparaciones if c.severidad == severidad)


@dataclass
class CifrasDeclaradas:
    """Lo que la liquidación va a llevar al formulario, por casilla."""

    casillas: Dict[int, Decimal]
    compras_con_factura_electronica: Decimal = CERO
    uvt: Decimal = CERO
    tope_compras_uvt: Decimal = Decimal("240")

    def c(self, *numeros: int) -> Decimal:
        return sum((self.casillas.get(n, CERO) for n in numeros), CERO)

    @property
    def ingresos_brutos(self) -> Decimal:
        # Ingresos brutos de todas las cédulas y ganancias ocasionales.
        return self.c(32, 43, 58, 74, 99, 104, 107, 108, 109, 112)


# ---------------------------------------------------------------------------
# 1. Los topes
# ---------------------------------------------------------------------------


def _numero_de_tope(etiqueta: str) -> Optional[int]:
    m = re.search(r"Tope\s+(\d)", etiqueta or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


def cuadrar_topes(
    registros: Sequence[Registro],
    topes: Dict[str, Decimal],
    umbrales: Optional[Dict[int, Decimal]] = None,
) -> List[CuadreDeTope]:
    """Reconstruye cada tope desde el detalle y lo compara con el reportado."""
    umbrales = umbrales or {}
    cuadres: List[CuadreDeTope] = []
    for etiqueta, valor_tope in topes.items():
        numero = _numero_de_tope(etiqueta)
        if numero is None:
            continue
        miembros = [r for r in registros if r.tope == numero]
        suma = sum((r.valor_propio for r in miembros), CERO)
        pisos = [r.valor for r in registros if r.piso_de_tope == numero]
        piso = max(pisos) if pisos else None
        esperado = max(suma, piso) if piso is not None else suma
        cuadra = abs(esperado - valor_tope) < _PESO

        if piso is not None and piso >= suma:
            explicacion = (
                f"El tope toma el patrimonio declarado el año anterior "
                f"({pesos(piso)}) porque es mayor que la suma de lo reportado por "
                f"terceros este año ({pesos(suma)})."
            )
        elif piso is not None:
            explicacion = (
                f"El tope toma la suma de lo reportado por terceros ({pesos(suma)}) "
                f"porque supera el patrimonio declarado el año anterior "
                f"({pesos(piso)})."
            )
        else:
            explicacion = f"Suma de {len(miembros)} registro(s) del archivo."
        if not cuadra:
            explicacion += (
                f" No cuadra: el detalle da {pesos(esperado)} y el archivo reporta "
                f"{pesos(valor_tope)}. Puede haber un registro que este programa no "
                f"supo asociar al tope, o un formato de archivo distinto."
            )

        umbral = umbrales.get(numero)
        cuadres.append(
            CuadreDeTope(
                numero=numero,
                nombre=NOMBRES_TOPE.get(numero, etiqueta),
                etiqueta=etiqueta,
                valor_tope=valor_tope,
                suma_detalle=suma,
                piso=piso,
                valor_esperado=esperado,
                cuadra=cuadra,
                umbral=umbral,
                supera_umbral=(valor_tope >= umbral) if umbral is not None else None,
                registros=[
                    DetalleTope(r.detalle, r.nombre_reportante, r.valor,
                                r.valor_propio, r.participacion)
                    for r in miembros
                ],
                explicacion=explicacion,
            )
        )
    return sorted(cuadres, key=lambda c: c.numero)


# ---------------------------------------------------------------------------
# 2 y 3. Lo declarado frente a lo reportado
# ---------------------------------------------------------------------------


def _suma_por_renglon(registros: Sequence[Registro], renglon: int) -> Optional[Decimal]:
    """Suma de los registros que la DIAN asigna a un renglón concreto.

    Devuelve None si el archivo no trae ninguno: «la DIAN no reporta nada» y
    «la DIAN reporta cero» no son lo mismo.
    """
    propios = [
        r for r in registros
        if renglon in r.renglones() and not r.renglones_son_condicionales
    ]
    if not propios:
        return None
    return sum((r.valor_propio for r in propios), CERO)


def _comparar_piso(clave, titulo, casillas, dian, declarado, que) -> Comparacion:
    """Para cifras donde declarar MENOS que la DIAN es el riesgo."""
    if dian is None:
        return Comparacion(clave, titulo, casillas, None, declarado, None, SIN_DATO,
                           f"La exógena no trae {que}.")
    diferencia = declarado - dian
    if diferencia < -TOLERANCIA:
        return Comparacion(
            clave, titulo, casillas, dian, declarado, diferencia, ALTA,
            f"Se declaran {pesos(declarado)} y los terceros le reportaron a la DIAN "
            f"{pesos(dian)}: faltan {pesos(-diferencia)}. Es la diferencia que origina "
            f"un requerimiento; o falta registrar algo, o hay que tener el soporte "
            f"de por qué la cifra del tercero está mal.",
        )
    return Comparacion(
        clave, titulo, casillas, dian, declarado, diferencia, OK,
        f"Lo declarado cubre lo que la DIAN tiene reportado ({que}).",
    )


def _comparar_patrimonio(
    tope: Optional[Decimal],
    de_terceros: Optional[Decimal],
    anio_anterior: Optional[Decimal],
    declarado: Decimal,
) -> Comparacion:
    """Patrimonio bruto contra el Tope 2, distinguiendo de dónde sale el tope.

    El Tope 2 es el mayor entre lo que reportaron los terceros y lo que el
    propio contribuyente declaró el año anterior. No son el mismo riesgo:
    declarar menos de lo que un tercero reportó es una omisión que la DIAN
    puede probar; declarar menos que el año pasado es normal si se vendió o se
    gastó algo, y solo pide tener la explicación.
    """
    if de_terceros is None and anio_anterior is None:
        return _comparar_piso("PATRIMONIO", "Patrimonio bruto", "29", tope,
                              declarado, "patrimonio")
    terceros = de_terceros or CERO
    if declarado < terceros - TOLERANCIA:
        return Comparacion(
            "PATRIMONIO", "Patrimonio bruto", "29", terceros, declarado,
            declarado - terceros, ALTA,
            f"Se declaran {pesos(declarado)} de patrimonio bruto y los terceros le "
            f"reportaron a la DIAN bienes por {pesos(terceros)}: faltan "
            f"{pesos(terceros - declarado)}. Es la diferencia que origina un "
            f"requerimiento; o falta registrar un bien, o hay que tener el soporte "
            f"de por qué la cifra del tercero está mal.",
        )
    if anio_anterior is not None and declarado < anio_anterior - TOLERANCIA:
        return Comparacion(
            "PATRIMONIO", "Patrimonio bruto", "29", anio_anterior, declarado,
            declarado - anio_anterior, MEDIA,
            f"Se declaran {pesos(declarado)} de patrimonio bruto, que cubren lo que "
            f"reportaron los terceros ({pesos(terceros)}) pero son "
            f"{pesos(anio_anterior - declarado)} menos de lo declarado el año "
            f"anterior ({pesos(anio_anterior)}). No es un error si se vendió o se "
            f"gastó algo; conviene tener claro qué salió del patrimonio y si esa "
            f"venta dejó un ingreso o una ganancia ocasional.",
        )
    return Comparacion(
        "PATRIMONIO", "Patrimonio bruto", "29", tope, declarado,
        (declarado - tope) if tope is not None else None, OK,
        "Lo declarado cubre lo reportado por terceros y lo declarado el año anterior.",
    )


def comparar(
    registros: Sequence[Registro],
    topes: Dict[int, Decimal],
    declarado: CifrasDeclaradas,
    patrimonio_de_terceros: Optional[Decimal] = None,
    patrimonio_anio_anterior: Optional[Decimal] = None,
) -> List[Comparacion]:
    salida: List[Comparacion] = []

    # --- Patrimonio bruto contra el Tope 2 --------------------------------
    salida.append(_comparar_patrimonio(
        topes.get(2), patrimonio_de_terceros, patrimonio_anio_anterior,
        declarado.c(29)))

    # --- Ingresos brutos contra el Tope 1 ---------------------------------
    salida.append(_comparar_piso(
        "INGRESOS", "Ingresos brutos de todas las cédulas",
        "32, 43, 58, 74, 99, 107, 108 y 112", topes.get(1),
        declarado.ingresos_brutos, "ingresos"))

    # --- Ganancias ocasionales contra los registros asignados a la 112 ----
    go_dian = _suma_por_renglon(registros, 112)
    if go_dian is not None:
        salida.append(_comparar_piso(
            "GANANCIA_OCASIONAL", "Ingresos por ganancias ocasionales", "112",
            go_dian, declarado.c(112), "ventas de bienes y otros ingresos ocasionales"))

    # --- Retenciones contra los registros asignados a la 132 --------------
    ret_dian = _suma_por_renglon(registros, 132)
    ret_decl = declarado.c(132)
    if ret_dian is None:
        if ret_decl > CERO:
            salida.append(Comparacion(
                "RETENCIONES", "Retenciones en la fuente", "132", None, ret_decl, None,
                MEDIA,
                f"Se restan {pesos(ret_decl)} de retenciones y la exógena no trae "
                f"ninguna. No es un error —no todos los agentes retenedores aparecen "
                f"en el archivo—, pero cada peso debe tener su certificado.",
            ))
    else:
        diferencia = ret_decl - ret_dian
        if diferencia > TOLERANCIA:
            salida.append(Comparacion(
                "RETENCIONES", "Retenciones en la fuente", "132", ret_dian, ret_decl,
                diferencia, MEDIA,
                f"Se restan {pesos(ret_decl)} de retenciones y los terceros "
                f"reportaron {pesos(ret_dian)}: {pesos(diferencia)} no aparecen en la "
                f"exógena. Hay que tener el certificado de retención que los "
                f"respalde, porque la DIAN los va a pedir.",
            ))
        elif diferencia < -TOLERANCIA:
            salida.append(Comparacion(
                "RETENCIONES", "Retenciones en la fuente", "132", ret_dian, ret_decl,
                diferencia, OPORTUNIDAD,
                f"Los terceros reportaron {pesos(ret_dian)} de retenciones y solo se "
                f"están restando {pesos(ret_decl)}: quedan {pesos(-diferencia)} que el "
                f"contribuyente ya pagó y no está descontando del impuesto.",
            ))
        else:
            salida.append(Comparacion(
                "RETENCIONES", "Retenciones en la fuente", "132", ret_dian, ret_decl,
                diferencia, OK, "Las retenciones restadas coinciden con las reportadas.",
            ))

    # --- Saldo a favor del año anterior contra la 131 ---------------------
    saldo_dian = _suma_por_renglon(registros, 131)
    saldo_decl = declarado.c(131)
    if saldo_dian is not None and saldo_decl - saldo_dian > TOLERANCIA:
        salida.append(Comparacion(
            "SALDO_A_FAVOR", "Saldo a favor del año anterior", "131", saldo_dian,
            saldo_decl, saldo_decl - saldo_dian, ALTA,
            f"Se arrastra un saldo a favor de {pesos(saldo_decl)} y la DIAN registra "
            f"{pesos(saldo_dian)} sin devolver ni compensar. Arrastrar un saldo que ya "
            f"se devolvió o que no existe es una inexactitud.",
        ))
    elif saldo_dian is not None and saldo_dian - saldo_decl > TOLERANCIA:
        salida.append(Comparacion(
            "SALDO_A_FAVOR", "Saldo a favor del año anterior", "131", saldo_dian,
            saldo_decl, saldo_decl - saldo_dian, OPORTUNIDAD,
            f"La DIAN registra un saldo a favor de {pesos(saldo_dian)} del año "
            f"anterior y solo se están imputando {pesos(saldo_decl)}.",
        ))

    # --- Compras con factura electrónica: la deducción del 1 % ------------
    beneficio = [
        r.valor for r in registros
        if "susceptible de beneficio" in (r.detalle or "").lower()
    ]
    if beneficio:
        fe_dian = sum(beneficio, CERO)
        fe_decl = declarado.compras_con_factura_electronica
        tope_pesos = declarado.tope_compras_uvt * declarado.uvt
        if fe_decl - fe_dian > TOLERANCIA:
            salida.append(Comparacion(
                "COMPRAS_FE", "Compras con factura electrónica (deducción del 1 %)",
                "28", fe_dian, fe_decl, fe_decl - fe_dian, MEDIA,
                f"Se registraron {pesos(fe_decl)} de compras con factura electrónica "
                f"y la DIAN solo reconoce {pesos(fe_dian)} como susceptibles del "
                f"beneficio. La deducción del 1 % sobre el exceso no tiene respaldo.",
            ))
        elif fe_dian - fe_decl > TOLERANCIA:
            posible = (fe_dian * Decimal("0.01")).quantize(_PESO)
            actual = (fe_decl * Decimal("0.01")).quantize(_PESO)
            if tope_pesos > CERO:
                posible, actual = min(posible, tope_pesos), min(actual, tope_pesos)
            if posible > actual:
                salida.append(Comparacion(
                    "COMPRAS_FE", "Compras con factura electrónica (deducción del 1 %)",
                    "28", fe_dian, fe_decl, fe_decl - fe_dian, OPORTUNIDAD,
                    f"La DIAN reconoce {pesos(fe_dian)} en compras con factura "
                    f"electrónica susceptibles del beneficio y solo se registraron "
                    f"{pesos(fe_decl)}. Registrarlas daría {pesos(posible - actual)} más "
                    f"de deducción (1 % de las compras, art. 336 num. 5 ET).",
                ))
        else:
            salida.append(Comparacion(
                "COMPRAS_FE", "Compras con factura electrónica (deducción del 1 %)",
                "28", fe_dian, fe_decl, fe_decl - fe_dian, OK,
                "Las compras registradas coinciden con las que reconoce la DIAN.",
            ))

    # --- Indicios: gastar o mover más de lo que se declara ganar ----------
    #
    # No son errores. Son las comparaciones con las que la DIAN escoge a quién
    # revisar, y tienen explicaciones legítimas: préstamos, traslados entre
    # cuentas propias, ahorros de años anteriores. Lo que el contador necesita
    # es saberlo antes de presentar, para tener la explicación lista.
    ingresos = declarado.ingresos_brutos
    gasto = topes.get(3, CERO) + topes.get(5, CERO)
    if gasto > ingresos + TOLERANCIA and gasto > CERO:
        salida.append(Comparacion(
            "INDICIO_GASTO", "Consumos y compras frente a ingresos declarados",
            "Topes 3 y 5", gasto, ingresos, ingresos - gasto, MEDIA,
            f"Los consumos con tarjeta y las compras reportadas suman {pesos(gasto)} y "
            f"los ingresos declarados son {pesos(ingresos)}. Gastar más de lo que se "
            f"declara ganar es un indicio que la DIAN revisa: conviene tener claro "
            f"con qué se pagó (ahorros, préstamos, ingresos no gravados).",
        ))
    movimientos = topes.get(4, CERO)
    if movimientos > ingresos + TOLERANCIA and movimientos > CERO:
        salida.append(Comparacion(
            "INDICIO_MOVIMIENTOS", "Consignaciones e inversiones frente a ingresos",
            "Tope 4", movimientos, ingresos, ingresos - movimientos, MEDIA,
            f"Las consignaciones, depósitos e inversiones reportadas suman "
            f"{pesos(movimientos)} y los ingresos declarados son {pesos(ingresos)}. "
            f"Tiene explicaciones legítimas —traslados entre cuentas propias, "
            f"préstamos, reinversión de un CDT—, pero hay que poder demostrarlas.",
        ))

    return salida


def cruzar(
    registros: Sequence[Registro],
    topes: Dict[str, Decimal],
    declarado: CifrasDeclaradas,
    umbrales: Optional[Dict[int, Decimal]] = None,
) -> ResultadoCruce:
    cuadres = cuadrar_topes(registros, topes, umbrales)
    por_numero = {c.numero: c.valor_tope for c in cuadres}
    tope_2 = next((c for c in cuadres if c.numero == 2), None)
    comparaciones = comparar(
        registros, por_numero, declarado,
        patrimonio_de_terceros=tope_2.suma_detalle if tope_2 else None,
        patrimonio_anio_anterior=tope_2.piso if tope_2 else None,
    )

    pendientes = [r for r in registros if r.renglones_son_condicionales]
    informativos = [
        r for r in registros
        if r.tope is None and r.piso_de_tope is None and not r.renglones()
        and "susceptible de beneficio" not in (r.detalle or "").lower()
    ]

    diagnosticos: List[str] = []
    descuadrados = [c for c in cuadres if not c.cuadra]
    if descuadrados:
        nombres = ", ".join(c.etiqueta for c in descuadrados)
        diagnosticos.append(
            f"No se pudo reconstruir desde el detalle: {nombres}. Las comparaciones "
            f"siguen usando el tope que reporta el archivo, pero conviene revisar "
            f"que el archivo se haya leído completo."
        )
    if pendientes:
        total = sum((r.valor for r in pendientes), CERO)
        diagnosticos.append(
            f"{len(pendientes)} registro(s) por {pesos(total)} no tienen un renglón "
            f"asignado por la DIAN (dependen de qué bien o derecho sea). No entran "
            f"en ninguna comparación hasta que se registren como activo, deuda o "
            f"ganancia ocasional."
        )
    return ResultadoCruce(cuadres, comparaciones, pendientes, informativos, diagnosticos)
