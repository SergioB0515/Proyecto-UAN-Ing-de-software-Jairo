"""El borrador del formulario 210: casillas, marcas y el PDF para transcribir."""

from decimal import Decimal as D

from modulos.liquidacion import borrador_210
from modulos.liquidacion.cedula_general import DEDUCCION_OTRA, DEDUCCION_VIVIENDA, EXENTA_AFC
from modulos.liquidacion.formulario_210 import CASILLAS_2024
from modulos.liquidacion.motor import (
    ConceptoDepuracion,
    GananciasOcasionales,
    InsumosLiquidacion,
    Patrimonio,
    RentasDeTrabajo,
    RentasPorSubcedula,
    liquidar,
)
from modulos.liquidacion import plantillas
from modulos.parametros.tablas_oficiales import PARAMETROS_POR_ANIO

P = PARAMETROS_POR_ANIO[2025]


def _liq(**kw):
    kw.setdefault("patrimonio", Patrimonio(patrimonio_bruto=D("300000000"), deudas=D("50000000")))
    return liquidar(InsumosLiquidacion(anio_gravable=2025, **kw), P)


def test_toda_casilla_que_emite_el_motor_existe_en_el_formulario():
    liq = _liq(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("150000000")),
        no_laborales=RentasPorSubcedula(ingresos_brutos=D("80000000")),
        ganancias_ocasionales=GananciasOcasionales(ingresos=D("40000000"), costos=D("10000000")),
        numero_dependientes=1,
        retenciones_en_la_fuente=D("5000000"),
        anticipo_pagado_anio_anterior=D("1000000"),
        saldo_a_favor_anio_anterior=D("500000"),
    )
    numeros = [r.casilla for r in liq.renglones if r.casilla]
    assert numeros
    for numero in numeros:
        assert numero in CASILLAS_2024, numero
    # Ninguna casilla sale dos veces: dos renglones peleando por la misma
    # casilla dejarían en el PDF el que casualmente se emitió de último.
    assert len(numeros) == len(set(numeros))


def test_la_liquidacion_privada_sigue_la_aritmetica_del_formulario():
    """126 = 121 − 125; 129 = 126 + 127; 134 = 129 + 133 − 130 − 131 − 132."""
    liq = _liq(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("250000000")),
        ganancias_ocasionales=GananciasOcasionales(ingresos=D("60000000"), costos=D("20000000")),
        otros_descuentos_tributarios=D("2000000"),
        retenciones_en_la_fuente=D("9000000"),
        anticipo_pagado_anio_anterior=D("3000000"),
    )
    c = {r.casilla: r.valor for r in liq.renglones if r.casilla}
    assert c[126] == c[121] - c[125]
    assert c[129] == c[126] + c[127]
    assert c[136] == c[129] + c[133] - c[130] - c[132]
    assert c[115] == c[112] - c[113]


def test_los_descuentos_no_se_comen_el_impuesto_de_ganancias_ocasionales():
    """En el formulario los descuentos (125) se restan del impuesto de renta
    (121) y el de ganancias ocasionales entra después, en la 127.
    """
    liq = _liq(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("60000000")),
        ganancias_ocasionales=GananciasOcasionales(ingresos=D("100000000")),
        otros_descuentos_tributarios=D("500000000"),
    )
    c = {r.casilla: r.valor for r in liq.renglones if r.casilla}
    assert c[125] == c[121]
    assert c[126] == D("0")
    assert c[129] == c[127] > D("0")
    assert any("no pueden exceder el impuesto sobre la renta" in d for d in liq.diagnosticos)


def test_la_casilla_140_se_marca_cuando_los_costos_superan_el_60_por_ciento():
    def con_costos(costos):
        return _liq(trabajo=RentasDeTrabajo(
            ingresos_sin_vinculo_laboral=D("100000000"),
            costos_y_gastos_sin_vinculo_laboral=D(costos),
            opta_por_costos_y_gastos=True,
        ))
    assert 140 in con_costos("60000001").casillas_marcadas
    assert 140 not in con_costos("60000000").casillas_marcadas
    assert any("casilla 140" in d for d in con_costos("70000000").diagnosticos)


def test_el_catalogo_manda_cada_plantilla_a_su_fila_del_formulario():
    assert plantillas.obtener("INTERESES_VIVIENDA").fila == DEDUCCION_VIVIENDA
    assert plantillas.obtener("AHORRO_AFC").fila == EXENTA_AFC
    assert plantillas.obtener("APORTES_VOLUNTARIOS_PENSION").fila == EXENTA_AFC
    assert plantillas.obtener("GMF").fila == DEDUCCION_OTRA
    # El art. 387 exige relación laboral: no se reparte, va a rentas de trabajo.
    assert plantillas.obtener("MEDICINA_PREPAGADA").subcedula_sugerida == "TRABAJO"
    assert plantillas.obtener("INTERESES_VIVIENDA").subcedula_sugerida is None


def test_el_pdf_se_genera_y_dice_que_es_un_borrador():
    liq = _liq(
        trabajo=RentasDeTrabajo(ingresos_brutos=D("120000000")),
        conceptos_depuracion=[ConceptoDepuracion(
            "Intereses de vivienda", D("10000000"), True, "Art. 119 ET",
            "INTERESES_VIVIENDA", None, DEDUCCION_VIVIENDA)],
    )
    casillas = borrador_210.construir_casillas(liq.renglones)
    assert casillas[38] == D("10000000")
    assert casillas[134] == casillas[136]
    pdf = borrador_210.a_pdf(borrador_210.Borrador210(
        nombre="Contribuyente de prueba", nit="1000000000", anio_gravable=2025,
        casillas=casillas, marcadas=liq.casillas_marcadas, numero_dependientes=0,
        diagnosticos=liq.diagnosticos, notas=liq.notas,
    ))
    assert pdf.startswith(b"%PDF")

    from pypdf import PdfReader
    import io
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "BORRADOR" in texto
    assert "No es el formulario oficial" in texto
    assert "120.000.000" in texto


def test_las_casillas_que_el_motor_no_calcula_no_se_imprimen_en_cero():
    """Un cero impreso se lee como «calculado y dio cero»."""
    liq = _liq(trabajo=RentasDeTrabajo(ingresos_brutos=D("50000000")))
    casillas = borrador_210.construir_casillas(liq.renglones)
    for numero in borrador_210.CASILLAS_NO_CALCULADAS:
        assert numero not in casillas
