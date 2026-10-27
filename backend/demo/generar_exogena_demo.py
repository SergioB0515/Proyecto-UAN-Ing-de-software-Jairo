"""Genera los archivos de exógena que se cargan EN VIVO durante la demo.

El importador de la aplicación solo acepta un Excel con la estructura del
reporte «Consulta de Información reportada por terceros» de la DIAN, así que
este script la reproduce fila por fila.

Uso, desde la carpeta ``backend/``:

    python demo/generar_exogena_demo.py

Deja los archivos en ``backend/demo/archivos/``:

  * ``exogena_osorio_pena_2025.xlsx``  — archivo válido de Sandra Milena
    Osorio Peña, el contribuyente que la semilla deja SIN exógena. Al cargarlo
    la conciliación produce de una vez un COINCIDE, una DISCREPANCIA, un
    NO_DECLARADO y un NO_REPORTADO_POR_TERCERO.
  * ``exogena_con_filas_invalidas.xlsx`` — mismo archivo con dos filas cuyo
    valor no es numérico, para mostrar que el importador las reporta como
    errores en vez de caerse.
  * ``no_es_un_excel.txt`` — para mostrar el rechazo de archivos que no son
    Excel.

Los NIT, nombres y cifras son ficticios.
"""

from __future__ import annotations

import os
from typing import List, Optional, Sequence

from openpyxl import Workbook

ANIO = 2025
CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archivos")

CONSULTANTE_ID = "1015442308"
CONSULTANTE_NOMBRE = "SANDRA MILENA OSORIO PEÑA"

TOPES = [
    ("Tope 1 - Ingresos", 64_800_000),
    ("Tope 2 - Patrimonio", 72_650_000),
    ("Tope 3 - Consumo TC", 7_200_000),
    ("Tope 4 - Movimiento", 81_300_000),
    ("Tope 5 - Compras", 6_400_000),
]

# (nit, nombre, detalle, valor, uso sugerido, información adicional)
REGISTROS = [
    ("860006555", "CLINICA DEL COUNTRY S A",
     "Pagos por salarios (Concepto: 5001)", 64_800_000,
     "Tope 1: Ingresos brutos | R32 Rentas de trabajo", None),
    # Declaró 11.300.000 -> diferencia de 3.550.000: DISCREPANCIA.
    ("890903938", "BANCOLOMBIA S A",
     "Saldo de cuentas de ahorro y corrientes a 31 de diciembre "
     "(Concepto: 1110)", 14_850_000,
     "Tope 2: Patrimonio | R29 Patrimonio Bruto",
     "Número de Cuenta / Documento: 20100049871"),
    # No lo declaró -> NO_DECLARADO.
    ("830025281", "ARRENDAMIENTOS LA COLINA S A S",
     "Arrendamientos de bienes inmuebles (Concepto: 5008)", 9_600_000,
     "Tope 1: Ingresos brutos | R47 Rentas no laborales",
     "Fecha de la Transacción: 20251130"),
    ("890903938", "BANCOLOMBIA S A",
     "Total consumos o gastos con tarjeta Crédito o Débito (Concepto: 1023)",
     7_200_000, "Tope 3: Consumos TC", "Clase de Tarjeta: *4* Débito"),
    ("860006555", "CLINICA DEL COUNTRY S A",
     "Retención en la fuente practicada por salarios", 4_536_000,
     "R132 Retenciones año gravable a declarar", None),
    (CONSULTANTE_ID, CONSULTANTE_NOMBRE,
     "Total patrimonio bruto declarado en el año anterior", 69_400_000,
     None, None),
]

ENCABEZADOS = [
    "NIT", "Nombre / Razón Social", "NIT",
    "Nombre/Razón Social reportada por el tercero", "Detalle", "Valor",
    "Uso declaración Sugerida", "Información  Adicional ",
]


def _construir(registros: Sequence[tuple]) -> Workbook:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Reporte"

    def fila(valores: List[Optional[object]]) -> None:
        hoja.append(valores + [None] * (8 - len(valores)))

    fila([None, None, "Consulta de Información reportada por terceros"])
    fila(["ADVERTENCIA: Esta información corresponde a la fecha de corte del "
          "proceso y puede cambiar."])
    fila(["Fecha corte del proceso: ", None, f"{ANIO + 1}-03-14 00:00:00"])
    fila([f"Año al que se refiere la consulta:", None, str(ANIO)])
    fila(["Identificación del consultante"])
    fila(["Tipo de documento:", None, "C. C."])
    fila(["Identificación:", None, CONSULTANTE_ID])
    fila(["Nombres / Razón social:", None, CONSULTANTE_NOMBRE])
    fila([])
    fila(["Si esta información presenta inconsistencias, debe comunicarse con "
          "el tercero que la reportó."])
    fila(["IMPORTANTE: Para cumplir con su obligación de declarar, la "
          "información aquí reportada es un punto de partida."])
    fila([])
    fila(["Persona que reporta", None, "Información reportada"])
    fila(ENCABEZADOS)

    for etiqueta, valor in TOPES:
        fila([None, None, None, None, etiqueta, valor])

    for nit, nombre, detalle, valor, uso, info in registros:
        fila([nit, nombre, CONSULTANTE_ID, CONSULTANTE_NOMBRE, detalle, valor,
              uso, info])

    anchos = {"A": 14, "B": 34, "C": 14, "D": 30, "E": 56, "F": 16, "G": 46,
              "H": 44}
    for columna, ancho in anchos.items():
        hoja.column_dimensions[columna].width = ancho
    return libro


def main() -> int:
    os.makedirs(CARPETA, exist_ok=True)

    valido = os.path.join(CARPETA, "exogena_osorio_pena_2025.xlsx")
    _construir(REGISTROS).save(valido)

    con_errores = list(REGISTROS)
    con_errores.insert(2, ("900123456", "COMERCIALIZADORA EJEMPLO S A S",
                           "Compras de bienes (Concepto: 5005)", "N/D",
                           "Tope 5: Compras", None))
    con_errores.append(("901987654", "SERVICIOS TEMPORALES EJEMPLO LTDA",
                        "Servicios prestados (Concepto: 5004)", "",
                        "Tope 1: Ingresos brutos", None))
    invalido = os.path.join(CARPETA, "exogena_con_filas_invalidas.xlsx")
    _construir(con_errores).save(invalido)

    no_excel = os.path.join(CARPETA, "no_es_un_excel.txt")
    with open(no_excel, "w", encoding="utf-8") as archivo:
        archivo.write(
            "Este archivo no es un Excel de la DIAN. Sirve para mostrar que "
            "la aplicación lo rechaza en vez de intentar procesarlo.\n"
        )

    for ruta in (valido, invalido, no_excel):
        print("Generado:", ruta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
