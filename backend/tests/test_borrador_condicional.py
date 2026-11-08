"""Pruebas del borrador por renglón frente a sugerencias condicionales.

El archivo de la DIAN no siempre asigna un renglón. A veces ofrece un menú:
«Según el bien o derecho reportado se puede usar en renglones como ... | R112
... | R29 Patrimonio Bruto | R30 Deudas». Tomar esos renglones como
definitivos suma el mismo valor en todos y cuenta la misma plata como
patrimonio, como deuda y como ganancia ocasional a la vez.

Se detectó con un archivo real: el borrador decía R29 = $372.035.792 cuando el
propio archivo reportaba un tope de patrimonio de $282.551.008.
"""

import io

import openpyxl
import pytest

from modulos.exogena.servicios import (
    _es_sugerencia_condicional,
    parsear_archivo_exogena,
)

USO_CONDICIONAL = (
    "Según el bien o derecho reportado se puede usar en renglones como "
    "Tope 2: Patrimonio | R112 Ingresos por ganancias ocasionales del país y "
    "del exterior | R114 Ganancias ocasionales no gravadas y exentas | "
    "R29 Patrimonio Bruto | R30 Deudas"
)
USO_DEFINIDO = (
    "Tope 2: Patrimonio | R29 Patrimonio Bruto | Se toma el mayor valor "
    "informado entre el avalúo y la base del impuesto predial"
)


@pytest.mark.parametrize(
    "uso, esperado",
    [
        (USO_CONDICIONAL, True),
        ("se pueden usar los renglones R29 y R30", True),
        ("Dependiendo de la naturaleza del pago | R32", True),
        (USO_DEFINIDO, False),
        ("R132 Retenciones año gravable a declarar", False),
        ("Tope 1: Ingresos brutos | R112 Ingresos por ganancias ocasionales", False),
        (None, False),
        ("", False),
    ],
)
def test_se_reconoce_cuando_la_sugerencia_es_condicional(uso, esperado):
    assert _es_sugerencia_condicional(uso) is esperado


def _archivo(filas) -> bytes:
    """Arma un Excel con la estructura del reporte de la DIAN."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja["A1"] = "Tipo de documento:"
    hoja["C1"] = "C. C."
    hoja["A2"] = "Identificación:"
    hoja["C2"] = "1000000000"
    hoja["A3"] = "Nombres / Razón social:"
    hoja["C3"] = "Contribuyente Ejemplo"
    hoja["A4"] = "NIT"
    hoja["B4"] = "Nombre / Razón Social"
    hoja["E4"] = "Detalle"
    hoja["F4"] = "Valor"
    hoja["G4"] = "Uso declaración Sugerida"
    for i, (nit, detalle, valor, uso) in enumerate(filas, start=5):
        hoja[f"A{i}"], hoja[f"B{i}"] = nit, "Tercero"
        hoja[f"E{i}"], hoja[f"F{i}"], hoja[f"G{i}"] = detalle, valor, uso
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_el_parser_marca_el_registro_condicional():
    resultado = parsear_archivo_exogena(
        _archivo(
            [
                ("900111222", "Adquisición en Notarías", 82500000, USO_CONDICIONAL),
                ("900333444", "Valor avalúo catastral", 206720992, USO_DEFINIDO),
            ]
        )
    )
    por_detalle = {r.detalle: r for r in resultado.registros}
    assert por_detalle["Adquisición en Notarías"].renglones_son_condicionales is True
    assert por_detalle["Valor avalúo catastral"].renglones_son_condicionales is False


def test_el_registro_condicional_conserva_los_renglones_posibles():
    """No se descartan: el contador necesita verlos para escoger."""
    resultado = parsear_archivo_exogena(
        _archivo([("900111222", "Adquisición en Notarías", 82500000, USO_CONDICIONAL)])
    )
    registro = resultado.registros[0]
    assert set(registro.renglones_sugeridos.split(", ")) == {"R112", "R114", "R29", "R30"}
    assert registro.uso_sugerido == USO_CONDICIONAL


def test_un_registro_definido_no_se_marca_aunque_traiga_varios_renglones():
    """Varios renglones no es lo mismo que renglones a elegir."""
    uso = "Tope 1: Ingresos brutos | R112 Ganancias ocasionales | R29 Patrimonio Bruto"
    resultado = parsear_archivo_exogena(
        _archivo([("900111222", "Venta de bien", 90000000, uso)])
    )
    assert resultado.registros[0].renglones_son_condicionales is False
