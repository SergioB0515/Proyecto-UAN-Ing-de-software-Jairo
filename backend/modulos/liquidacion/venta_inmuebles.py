"""Venta de inmuebles: costo fiscal, utilidad y tratamiento. Función pura.

- >= 2 años: ganancia ocasional (art. 300, casillas 112-115); si no, renta no laboral.
- Costo fiscal: max(art. 73 reajustado + mejoras y valorización, avalúo del
  año anterior art. 72). Uno de los dos, sin mezclar.
- Vivienda de habitación: 5.000 UVT exentas (art. 311-1), por participación
  (Concepto DIAN 6970 de 2024). La destinación a AFC o al crédito la confirma
  el contador.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from core.formato import pesos
from ..parametros.reajuste_activos import FUENTE, factor_art_73

CERO = Decimal("0")
UVT_EXENTAS_VIVIENDA = Decimal("5000")


def _peso(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _porcentaje(p: Decimal) -> str:
    """50.00 -> "50"; 33.50 -> "33,5". normalize() daría 1E+2 para 100."""
    texto = f"{p:f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def _mas_anios(f: date, n: int) -> date:
    return date(f.year + n, f.month, min(f.day, calendar.monthrange(f.year + n, f.month)[1]))


@dataclass
class VentaInmueble:
    descripcion: str
    tipo: str  # URBANO | RURAL_AGROPECUARIO | RURAL
    fecha_adquisicion: date
    fecha_venta: date
    valor_venta: Decimal
    costo_adquisicion: Decimal
    mejoras_y_valorizacion: Decimal = CERO
    avaluo_catastral_anterior: Optional[Decimal] = None
    es_casa_de_habitacion: bool = False
    porcentaje_participacion: Decimal = Decimal("100")
    retencion: Decimal = CERO
    # Año sin tabla: el contador escribe el factor del decreto.
    factor_manual: Optional[Decimal] = None


@dataclass
class ResultadoVenta:
    es_ganancia_ocasional: bool
    costo_reajustado: Optional[Decimal]
    factor: Optional[Decimal]
    costo_fiscal: Decimal
    metodo_costo: str  # ART_73 | ART_72
    utilidad: Decimal
    perdida: Decimal
    exenta: Decimal
    formula: str
    fuente: str
    avisos: List[str] = field(default_factory=list)


def calcular(venta: VentaInmueble, anio_gravable: int, uvt: Decimal) -> ResultadoVenta:
    avisos: List[str] = []
    es_go = venta.fecha_venta >= _mas_anios(venta.fecha_adquisicion, 2)

    factor = venta.factor_manual or factor_art_73(
        anio_gravable, venta.tipo, venta.fecha_adquisicion.year)
    fuente_factor = ("multiplicador escrito por el contador" if venta.factor_manual
                     else FUENTE.get(anio_gravable, ""))
    costo_reajustado = None
    if factor is None:
        avisos.append(
            f"No hay tabla del art. 73 cargada para {anio_gravable}: se usó el costo "
            f"de adquisición sin reajustar. Escriba el multiplicador del decreto de "
            f"ese año para no pagar impuesto sobre la inflación.")
        costo_reajustado = _peso(venta.costo_adquisicion + venta.mejoras_y_valorizacion)
    else:
        costo_reajustado = _peso(venta.costo_adquisicion * factor
                                 + venta.mejoras_y_valorizacion)

    avaluo = venta.avaluo_catastral_anterior
    if avaluo is not None and avaluo > costo_reajustado:
        costo, metodo = avaluo, "ART_72"
        explicacion = (f"Costo fiscal: avalúo catastral del año anterior {pesos(avaluo)} "
                       f"(art. 72), mayor que el costo reajustado {pesos(costo_reajustado)}")
    else:
        costo, metodo = costo_reajustado, "ART_73"
        explicacion = (
            f"Costo fiscal: {pesos(venta.costo_adquisicion)} × "
            f"{str(factor).replace('.', ',') if factor else '1'} "
            f"(art. 73, compra en {venta.fecha_adquisicion.year}"
            f"{', ' + fuente_factor if factor else ''})"
            + (f" + mejoras y valorización {pesos(venta.mejoras_y_valorizacion)}"
               if venta.mejoras_y_valorizacion else "")
            + f" = {pesos(costo_reajustado)}"
            + (f"; mayor que el avalúo catastral {pesos(avaluo)}" if avaluo is not None else "")
        )

    diferencia = venta.valor_venta - costo
    utilidad, perdida = max(diferencia, CERO), max(-diferencia, CERO)

    exenta = CERO
    if es_go and venta.es_casa_de_habitacion and utilidad > 0:
        tope = _peso(UVT_EXENTAS_VIVIENDA * uvt * venta.porcentaje_participacion / 100)
        exenta = min(utilidad, tope)
        avisos.append(
            f"Exención de casa de habitación: {pesos(exenta)} (hasta 5.000 UVT, "
            f"{_porcentaje(venta.porcentaje_participacion)} % de participación). Solo procede si el "
            f"dinero de la venta se depositó en una cuenta AFC o se usó para pagar el "
            f"crédito hipotecario del inmueble (art. 311-1 ET).")
    if perdida > 0:
        avisos.append(
            f"La venta deja una pérdida de {pesos(perdida)}. "
            + ("Una pérdida en ganancia ocasional no se resta de las rentas ordinarias "
               "ni de otras ganancias ocasionales." if es_go else
               "Entra como costo de las rentas no laborales del año."))
    if not es_go:
        avisos.append(
            "Se poseyó menos de dos años: la utilidad no es ganancia ocasional sino "
            "renta ordinaria (rentas no laborales), con la tarifa del art. 241.")

    destino = ("ganancia ocasional (art. 300 ET)" if es_go
               else "renta ordinaria: poseído menos de dos años (art. 300 ET)")
    formula = (f"{explicacion}. Venta {pesos(venta.valor_venta)} − costo fiscal "
               f"{pesos(costo)} = {'utilidad ' + pesos(utilidad) if utilidad else 'pérdida ' + pesos(perdida)}"
               f"; va como {destino}")
    return ResultadoVenta(es_go, costo_reajustado, factor, costo, metodo, utilidad,
                          perdida, exenta, formula,
                          "Arts. 69, 72, 73, 300 y 311-1 ET", avisos)
