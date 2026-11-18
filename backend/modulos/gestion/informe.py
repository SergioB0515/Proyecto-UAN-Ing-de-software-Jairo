"""Informe de la declaración para el cliente, en PDF.

El borrador del 210 es para el contador; este documento es para el
contribuyente: qué va a declarar, cuánto paga y hasta cuándo, de dónde sale la
cifra, qué tiene reportado la DIAN sobre él, qué documentos faltan y cuándo
queda en firme. Sin casillas ni artículos en el cuerpo: las normas van al pie.
"""

import io
import re
from datetime import date
from decimal import Decimal
from typing import List, Tuple
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlmodel import Session

from core.excepciones import ReporteExogenaNoEncontradoError
from ..contribuyentes.servicios import obtener_contribuyente
from . import servicios
from .modelos import EstadoDocumento

CERO = Decimal("0")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")


def fecha_larga(f: date) -> str:
    return f"{f.day} de {_MESES[f.month - 1]} de {f.year}"


def _pesos(v: Decimal) -> str:
    return "$" + f"{int(Decimal(v).quantize(Decimal('1'))):,}".replace(",", ".")


def generar(session: Session, contador, contribuyente_id: int, periodo_id: int
            ) -> Tuple[bytes, str]:
    contribuyente = obtener_contribuyente(session, contador.id, contribuyente_id)
    g = servicios.gestion(session, contador.id, contribuyente_id, periodo_id)
    docs = servicios.solicitud_documentos(session, contador.id, contribuyente_id, periodo_id)
    base = (g.presentaciones[-1].casillas if g.presentaciones else
            {r.casilla: Decimal(r.valor_declarable) for r in
             servicios.liquidacion.liquidar_periodo(
                 session, contador.id, contribuyente_id, periodo_id).renglones
             if r.casilla})
    c = lambda n: Decimal(base.get(n, CERO))  # noqa: E731

    riesgos: List[str] = []
    try:
        from ..conciliacion.servicios import cruzar_con_la_dian

        cruce = cruzar_con_la_dian(session, contador.id, contribuyente_id, periodo_id)
        riesgos = [k.mensaje for k in cruce.comparaciones if k.severidad == "ALTA"]
        hay_cruce = True
        # El cruce compara totales: un ingreso no declarado puede quedar tapado
        # por otros. La conciliación registro por registro no lo deja pasar.
        from ..conciliacion.modelos import EstadoConciliacion
        from ..conciliacion.servicios import conciliar_contribuyente

        conciliacion = conciliar_contribuyente(session, contador.id, contribuyente_id,
                                               periodo_id)
        for item in conciliacion.items:
            if item.estado == EstadoConciliacion.NO_DECLARADO:
                concepto = re.sub(r"\s*\(Concepto:\s*\d+\)", "", item.concepto).strip()
                quien = (item.nombre_reportante or "Un tercero").title()
                riesgos.append(
                    f"{quien} reportó «{concepto}» por "
                    f"{_pesos(Decimal(str(item.valor_exogena or 0)))}, y eso no está en la "
                    f"declaración. Necesitamos saber de qué se trata para incluirlo o "
                    f"tener el soporte de por qué no va.")
    except ReporteExogenaNoEncontradoError:
        hay_cruce = False

    buffer = io.BytesIO()
    margen = 2 * cm
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=margen, rightMargin=margen,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=f"Su declaración de renta {g.anio_gravable}")
    base_estilos = getSampleStyleSheet()
    titulo = base_estilos["Title"].clone("t", fontSize=16, leading=20, alignment=0)
    h = base_estilos["Heading3"].clone("h", fontSize=11.5, spaceBefore=12, spaceAfter=4,
                                       textColor=colors.HexColor("#1F3A5F"))
    p = base_estilos["BodyText"].clone("p", fontSize=10, leading=14)
    pequeno = p.clone("pq", fontSize=8, leading=10.5, textColor=colors.HexColor("#555555"))
    cifra = p.clone("cf", fontSize=20, leading=24, fontName="Helvetica-Bold")
    derecha = p.clone("d", alignment=TA_RIGHT)
    ancho = letter[0] - 2 * margen

    e: list = [
        Paragraph(f"Su declaración de renta del año gravable {g.anio_gravable}", titulo),
        Paragraph(f"{escape(contribuyente.nombre)} · NIT {escape(contribuyente.rut)}<br/>"
                  f"Preparado por {escape(contador.nombre)} · {fecha_larga(servicios._hoy())}",
                  pequeno),
        Spacer(1, 0.4 * cm),
    ]

    # --- El resultado ---------------------------------------------------
    if g.saldo_a_pagar > 0:
        resultado, texto = _pesos(g.saldo_a_pagar), "es el valor a pagar"
    elif g.saldo_a_favor > 0:
        resultado, texto = _pesos(g.saldo_a_favor), "es su saldo a favor"
    else:
        resultado, texto = "$0", "no tiene saldo a pagar ni a favor"
    e.append(Paragraph(resultado, cifra))
    e.append(Paragraph(texto + (" según la declaración presentada." if g.presentaciones
                                else " según el borrador preparado."), p))
    if g.fecha_presentacion:
        e.append(Paragraph(f"Se presentó el {fecha_larga(g.fecha_presentacion)}.", p))
    elif g.vencimiento and g.vencimiento < servicios._hoy():
        texto = (f"<b>El plazo para presentar venció el {fecha_larga(g.vencimiento)}.</b> "
                 f"La cifra ya incluye la sanción por extemporaneidad causada a hoy "
                 f"({_pesos(c(135))}), que sube cada mes que pase sin presentar.")
        if g.intereses is not None:
            texto += (f" Además se causan intereses de mora sobre el impuesto: "
                      f"{_pesos(g.intereses.valor)} a hoy, que suben cada día.")
            if g.intereses.meses_sin_tasa:
                texto += " (Cifra parcial: falta la tasa de algún mes.)"
        e.append(Paragraph(texto, p))
    elif g.vencimiento:
        pagar = " y pagar" if g.saldo_a_pagar > 0 else ""
        e.append(Paragraph(f"<b>Fecha límite para presentar{pagar}: "
                           f"{fecha_larga(g.vencimiento)}.</b> Después de esa fecha se "
                           f"cobra sanción por cada mes de retraso"
                           + (" e intereses de mora." if g.saldo_a_pagar > 0 else "."), p))

    # --- De dónde sale --------------------------------------------------
    e.append(Paragraph("De dónde sale la cifra", h))
    ingresos = sum((c(n) for n in (32, 43, 58, 74, 99, 107, 108)), CERO)
    filas = [
        ("Patrimonio líquido a 31 de diciembre (bienes menos deudas)", c(31)),
        ("Ingresos del año", ingresos),
        ("Renta sobre la que se calcula el impuesto", c(111)),
        ("Impuesto de renta, después de descuentos", c(126)),
        ("Impuesto de ganancias ocasionales (herencias, ventas de bienes, premios)", c(127)),
        ("Menos: retenciones que le practicaron durante el año", -c(132)),
        ("Más: anticipo del impuesto del año siguiente", c(133)),
        ("Menos: anticipo y saldo a favor del año anterior", -(c(130) + c(131))),
    ]
    if c(135) > 0:
        filas.append(("Más: sanciones", c(135)))
    # El impuesto de renta se muestra aunque sea cero: es lo que el cliente
    # busca primero.
    filas = [(t, v) for t, v in filas if v != 0 or t.startswith("Impuesto de renta")]
    tabla = Table([[Paragraph(escape(t), p), Paragraph(_pesos(v) if v >= 0 else
                                                      "−" + _pesos(-v), derecha)]
                   for t, v in filas], colWidths=[ancho * 0.72, ancho * 0.28])
    tabla.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    e.append(tabla)
    if c(133) > 0:
        e.append(Spacer(1, 0.15 * cm))
        e.append(Paragraph(
            "El anticipo es un pago adelantado del impuesto del próximo año que la ley "
            "obliga a incluir; se descuenta en la siguiente declaración.", pequeno))

    if g.comparativo:
        anterior = next((f for f in g.comparativo.filas if f.casilla == 126), None)
        if anterior and anterior.anterior is not None:
            e.append(Paragraph("Frente al año anterior", h))
            e.append(Paragraph(
                f"El impuesto de renta pasa de {_pesos(anterior.anterior)} a "
                f"{_pesos(anterior.actual or CERO)}.", p))

    # --- La DIAN --------------------------------------------------------
    e.append(Paragraph("Lo que la DIAN tiene reportado sobre usted", h))
    if not hay_cruce:
        e.append(Paragraph("No se cargó el reporte de información exógena, así que no "
                           "se pudo comparar con lo que terceros le reportaron a la DIAN.", p))
    elif riesgos:
        e.append(Paragraph("Hay diferencias que debemos resolver antes de presentar:", p))
        for r in riesgos:
            e.append(Paragraph("• " + escape(r), p))
    else:
        e.append(Paragraph("Lo que se va a declarar cubre lo que bancos, empleadores y "
                           "demás terceros le reportaron a la DIAN.", p))

    # --- Documentos -----------------------------------------------------
    pendientes = [d for d in docs.documentos if d.estado == EstadoDocumento.PENDIENTE]
    if pendientes:
        e.append(Paragraph("Documentos que todavía necesitamos", h))
        for d in pendientes:
            de = f" — {escape(d.tercero.title())}" if d.tercero else ""
            e.append(Paragraph(f"• {escape(d.descripcion)}{de}", p))

    # --- Firmeza --------------------------------------------------------
    e.append(Paragraph("Hasta cuándo puede revisarla la DIAN", h))
    if g.firmeza.fecha:
        e.append(Paragraph(f"La DIAN puede revisar esta declaración hasta el "
                           f"{fecha_larga(g.firmeza.fecha)}. Guarde los soportes al menos "
                           f"hasta esa fecha.", p))
    else:
        e.append(Paragraph("El plazo empieza a contar cuando se presente la declaración: "
                           "por regla general son tres años.", p))
    if g.beneficio_auditoria.meses and not g.presentaciones:
        e.append(Paragraph(
            f"Si se presenta y se paga a tiempo, la declaración queda en firme en solo "
            f"{g.beneficio_auditoria.meses} meses, porque el impuesto aumentó lo "
            f"suficiente frente al año anterior (beneficio de auditoría).", p))

    e.append(Spacer(1, 0.5 * cm))
    e.append(Paragraph(
        "Antes de presentar, avísenos si tiene ingresos, bienes o deudas que no nos haya "
        "informado. La información de la declaración y sus soportes es responsabilidad "
        "del contribuyente. Este informe es una explicación preparada por su contador y "
        "no reemplaza el formulario 210 de la DIAN.", pequeno))
    normas = ("Normas: arts. 336, 241, 807, 641 y 714 del Estatuto Tributario; "
              "beneficio de auditoría, art. 689-3 ET.")
    if g.firmeza.fecha:
        normas += f" Firmeza: {escape(g.firmeza.regla)} ({escape(g.firmeza.fuente)})."
    e.append(Paragraph(normas, pequeno))

    doc.build(e)
    return buffer.getvalue(), f"informe_renta_{contribuyente.rut}_{g.anio_gravable}.pdf"
