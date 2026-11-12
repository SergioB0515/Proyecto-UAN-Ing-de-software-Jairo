"""Borrador del formulario 210, casilla por casilla.

Qué es y qué no es
------------------
Es un papel de trabajo para transcribir: las mismas casillas del formulario 210,
con el mismo número y en el mismo orden, llenas con lo que calculó el motor.

No es el formulario oficial ni pretende parecerlo. El 210 solo se presenta desde
los servicios en línea de la DIAN, que recalculan cada total; el PDF que la
DIAN publica es de consulta y viene marcado «no diligenciable». Por eso este
documento no lleva la imagen de la DIAN y cada página va cruzada con la
leyenda de borrador.

Los valores van aproximados al múltiplo de mil más cercano (art. 577 ET), que es
como se digitan. Como cada casilla se aproxima por separado, un total puede
diferir hasta en mil pesos de la suma de sus partes ya aproximadas; el servicio
de la DIAN recalcula los totales a partir de lo digitado.
"""

import io
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .formulario_210 import (
    ADVERTENCIA_ANIO_NO_VERIFICADO,
    CASILLAS_2024,
    SUBCEDULAS,
    _GRILLA_CEDULA_GENERAL,
)

CERO = Decimal("0")

_ENCABEZADOS_GRILLA = (
    "Rentas de trabajo",
    "Rentas de trabajo sin vínculo laboral",
    "Rentas de capital",
    "Rentas no laborales",
)

# Las secciones que siguen a la grilla, en el orden del formulario.
_SECCIONES = (
    ("Patrimonio", (29, 30, 31)),
    ("Cédula general — totales", (28, 91, 92, 93, 94, 95, 96, 97, 98, 139)),
    ("Cédula de pensiones", (99, 100, 101, 102, 103)),
    ("Cédula de dividendos y participaciones", (104, 105, 106, 107, 108, 109, 110)),
    ("Renta líquida gravable", (111,)),
    ("Ganancias ocasionales", (112, 113, 114, 115)),
    ("Liquidación privada", tuple(range(116, 138))),
)

# Casillas que el motor no calcula. Se imprimen vacías y señaladas, no en cero:
# un cero impreso se lee como «calculado y dio cero».
CASILLAS_NO_CALCULADAS = {
    94: "pérdidas de 2018 y anteriores",
    95: "excesos de renta presuntiva",
    104: "dividendos de 2016 y anteriores",
    105: "dividendos de 2016 y anteriores",
    106: "dividendos de 2016 y anteriores",
    109: "dividendos del exterior",
    110: "dividendos del exterior",
    118: "impuesto del art. 240 sobre dividendos gravados",
    119: "dividendos de 2016 y anteriores",
    120: "dividendos del exterior",
    122: "impuestos pagados en el exterior",
    123: "donaciones",
    128: "impuestos pagados en el exterior",
    135: "sanciones",
}


@dataclass
class Borrador210:
    nombre: str
    nit: str
    anio_gravable: int
    casillas: Dict[int, Decimal]
    marcadas: List[int] = field(default_factory=list)
    numero_dependientes: Optional[int] = None
    diagnosticos: List[str] = field(default_factory=list)
    notas: List[str] = field(default_factory=list)


def construir_casillas(renglones) -> Dict[int, Decimal]:
    """Casilla → valor a declarar, a partir de los renglones del motor.

    Solo entran los renglones que el motor marcó con su número de casilla. La
    134 (saldo a pagar por impuesto) repite la 136 porque el borrador no
    liquida sanciones.
    """
    casillas: Dict[int, Decimal] = {}
    for renglon in renglones:
        numero = getattr(renglon, "casilla", None)
        if numero:
            casillas[numero] = Decimal(renglon.valor_declarable)
    if 136 in casillas:
        casillas[134] = casillas[136]
    return casillas


def _pesos(valor: Decimal) -> str:
    return f"{int(valor):,}".replace(",", ".")


def a_pdf(borrador: Borrador210) -> bytes:
    buffer = io.BytesIO()
    margen = 1.2 * cm
    ancho_util = letter[0] - 2 * margen
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, leftMargin=margen, rightMargin=margen,
        topMargin=margen, bottomMargin=1.6 * cm,
        title=f"Borrador formulario 210 — {borrador.nombre} — AG {borrador.anio_gravable}",
    )
    base = getSampleStyleSheet()
    titulo = base["Title"].clone("t", fontSize=13, leading=16, spaceAfter=2)
    sub = base["Normal"].clone("s", fontSize=8.5, leading=11, alignment=TA_CENTER,
                               textColor=colors.HexColor("#444444"))
    h = base["Heading4"].clone("h", fontSize=9.5, spaceBefore=8, spaceAfter=3)
    celda = base["BodyText"].clone("c", fontSize=7, leading=8.5)
    cab = celda.clone("cab", fontName="Helvetica-Bold", alignment=TA_CENTER,
                      textColor=colors.white)
    num = celda.clone("n", fontSize=6, alignment=TA_CENTER,
                      textColor=colors.HexColor("#555555"))
    val = celda.clone("v", fontSize=7.5, alignment=TA_RIGHT, fontName="Helvetica-Bold")
    vacio = val.clone("vac", fontName="Helvetica-Oblique", fontSize=6,
                      textColor=colors.HexColor("#999999"))
    nota = base["BodyText"].clone("nota", fontSize=7.5, leading=9.5)
    azul = colors.HexColor("#1F3A5F")
    gris = colors.HexColor("#E3E3E3")

    def valor_de(numero: int):
        if numero in CASILLAS_NO_CALCULADAS and numero not in borrador.casillas:
            return Paragraph("no calculada", vacio)
        return Paragraph(_pesos(borrador.casillas.get(numero, CERO)), val)

    e: list = [
        Paragraph("Borrador para transcripción — casillas del formulario 210", titulo),
        Paragraph(
            "Papel de trabajo. <b>No es el formulario oficial y no es válido para "
            "presentar:</b> la declaración se diligencia y se firma en los servicios "
            "en línea de la DIAN.", sub),
        Spacer(1, 0.25 * cm),
    ]
    datos = Table(
        [[Paragraph(f"<b>Contribuyente:</b> {escape(borrador.nombre)}", celda),
          Paragraph(f"<b>NIT:</b> {escape(borrador.nit)}", celda),
          Paragraph(f"<b>Año gravable:</b> {borrador.anio_gravable}", celda)]],
        colWidths=[ancho_util * 0.55, ancho_util * 0.25, ancho_util * 0.20],
    )
    datos.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
    e.append(datos)

    def tabla_lista(numeros):
        """Dos columnas de «n° · concepto · valor», como las del formulario."""
        mitad = (len(numeros) + 1) // 2
        izq, der = numeros[:mitad], numeros[mitad:]
        filas = []
        for i in range(mitad):
            fila = []
            for lado in (izq, der):
                if i < len(lado):
                    n = lado[i]
                    fila += [Paragraph(str(n), num),
                             Paragraph(escape(CASILLAS_2024[n].nombre), celda),
                             valor_de(n)]
                else:
                    fila += ["", "", ""]
            filas.append(fila)
        a_n, a_v = 0.7 * cm, 2.5 * cm
        a_c = (ancho_util - 2 * (a_n + a_v)) / 2
        t = Table(filas, colWidths=[a_n, a_c, a_v, a_n, a_c, a_v])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (0, -1), gris),
            ("BACKGROUND", (3, 0), (3, -1), gris),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ("LEFTPADDING", (0, 0), (0, -1), 1), ("RIGHTPADDING", (0, 0), (0, -1), 1),
            ("LEFTPADDING", (3, 0), (3, -1), 1), ("RIGHTPADDING", (3, 0), (3, -1), 1),
        ]))
        return t

    e.append(Paragraph("Patrimonio", h))
    e.append(tabla_lista(_SECCIONES[0][1]))

    # --- La grilla de la cédula general -----------------------------------
    e.append(Paragraph("Cédula general", h))
    a_n, a_v = 0.65 * cm, 2.45 * cm
    a_c = ancho_util - 4 * (a_n + a_v)
    filas = [[Paragraph("Concepto", cab)]
             + [x for enc in _ENCABEZADOS_GRILLA for x in (Paragraph(enc, cab), "")]]
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), azul),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]
    for k in range(4):
        estilo.append(("SPAN", (1 + 2 * k, 0), (2 + 2 * k, 0)))
        estilo.append(("LEFTPADDING", (1 + 2 * k, 1), (1 + 2 * k, -1), 1))
        estilo.append(("RIGHTPADDING", (1 + 2 * k, 1), (1 + 2 * k, -1), 1))
    for i, (nombre_fila, numeros) in enumerate(_GRILLA_CEDULA_GENERAL.items(), start=1):
        fila = [Paragraph(escape(nombre_fila), celda)]
        for k, n in enumerate(numeros):
            if n is None:
                fila += ["", ""]
                # Celda que no existe en el formulario: sombreada, no en cero.
                estilo.append(("BACKGROUND", (1 + 2 * k, i), (2 + 2 * k, i), gris))
                estilo.append(("SPAN", (1 + 2 * k, i), (2 + 2 * k, i)))
            else:
                fila += [Paragraph(str(n), num), valor_de(n)]
        filas.append(fila)
    grilla = Table(filas, colWidths=[a_c] + [a_n, a_v] * 4, repeatRows=1)
    grilla.setStyle(TableStyle(estilo))
    e.append(grilla)

    for nombre_seccion, numeros in _SECCIONES[1:]:
        e.append(Paragraph(nombre_seccion, h))
        e.append(tabla_lista(numeros))

    # --- Casillas de marca e informativas ---------------------------------
    e.append(Paragraph("Otras casillas", h))
    marca_140 = "Sí — marcar" if 140 in borrador.marcadas else "No"
    dependientes = ("—" if borrador.numero_dependientes is None
                    else str(borrador.numero_dependientes))
    otras = Table(
        [[Paragraph("138", num), Paragraph(escape(CASILLAS_2024[138].nombre), celda),
          Paragraph(dependientes, val),
          Paragraph("140", num), Paragraph(escape(CASILLAS_2024[140].nombre), celda),
          Paragraph(marca_140, val)]],
        colWidths=[0.7 * cm, (ancho_util - 6.4 * cm) / 2, 2.5 * cm] * 2,
    )
    otras.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("BACKGROUND", (0, 0), (0, -1), gris),
                               ("BACKGROUND", (3, 0), (3, -1), gris),
                               ("LEFTPADDING", (0, 0), (0, -1), 1),
                               ("RIGHTPADDING", (0, 0), (0, -1), 1),
                               ("LEFTPADDING", (3, 0), (3, -1), 1),
                               ("RIGHTPADDING", (3, 0), (3, -1), 1),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    e.append(otras)

    # --- Lo que hay que saber antes de transcribir ------------------------
    e.append(Paragraph("Antes de transcribir", h))
    avisos = [
        "Los valores están aproximados al múltiplo de mil más cercano (art. 577 ET). "
        "Cada casilla se aproxima por separado, así que un total puede diferir hasta "
        "en mil pesos de la suma de sus partes; el servicio de la DIAN recalcula los "
        "totales a partir de lo que se digita.",
        "Las casillas señaladas como «no calculada» no las maneja este borrador ("
        + "; ".join(f"{n}: {motivo}" for n, motivo in sorted(CASILLAS_NO_CALCULADAS.items())
                    if n not in borrador.casillas)
        + "). Si aplican al contribuyente, deben liquidarse aparte.",
    ]
    if borrador.anio_gravable != 2024:
        avisos.append(ADVERTENCIA_ANIO_NO_VERIFICADO)
    avisos.append(
        "La responsabilidad de la declaración es del contribuyente y del contador "
        "que la firma (art. 581 ET)."
    )
    for texto in avisos:
        e.append(Paragraph("• " + escape(texto), nota))

    if borrador.diagnosticos:
        e.append(Paragraph("Diagnósticos de la liquidación", h))
        for texto in borrador.diagnosticos:
            e.append(Paragraph("• " + escape(texto), nota))
    if borrador.notas:
        e.append(Paragraph("Notas", h))
        for texto in borrador.notas:
            e.append(Paragraph("• " + escape(texto), nota))

    def marca_de_agua(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 44)
        canvas.setFillColor(colors.HexColor("#C0392B"), alpha=0.10)
        canvas.translate(letter[0] / 2, letter[1] / 2)
        canvas.rotate(52)
        canvas.drawCentredString(0, 20, "BORRADOR")
        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawCentredString(0, -14, "NO VÁLIDO PARA PRESENTAR")
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(
            margen, 0.9 * cm,
            "Borrador de trabajo — no es el formulario oficial de la DIAN — "
            f"{borrador.nombre} — NIT {borrador.nit} — AG {borrador.anio_gravable}",
        )
        canvas.drawRightString(letter[0] - margen, 0.9 * cm, f"Página {_doc.page}")
        canvas.restoreState()

    doc.build(e, onFirstPage=marca_de_agua, onLaterPages=marca_de_agua)
    return buffer.getvalue()
