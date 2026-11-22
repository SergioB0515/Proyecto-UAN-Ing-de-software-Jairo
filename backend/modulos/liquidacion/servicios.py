"""Orquestación de la liquidación: lee la base, arma los insumos, llama al motor.

La base guarda float; aquí se convierte a Decimal con _dec(), vía str.
"""

from core.dinero import redondear_pesos
from core.formato import pesos
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from core.excepciones import (
    ActivoNoEncontradoError,
    AnioGravableNoSoportadoError,
    DeduccionNoEncontradaError,
    FuenteIngresoNoEncontradaError,
    PagoEfectivoNoEncontradoError,
    PerdidaNoEncontradaError,
    PlantillaNoEncontradaError,
    SinPeriodoAnteriorError,
)

from ..contribuyentes.modelos import Activo, FuenteIngreso, PeriodoFiscal
from ..contribuyentes.servicios import (
    listar_activos,
    listar_fuentes_ingreso,
    obtener_contribuyente,
    obtener_periodo_fiscal,
)
from ..parametros.tablas_oficiales import (
    ANIOS_SOPORTADOS,
    PARAMETROS_POR_ANIO,
    ParametrosAnuales,
)
from ..inventario.servicios import TIPOS_CON_INVENTARIO
from ..movimientos.servicios import calcular_costo_ventas
from . import clasificador, motor, plantillas, sanciones
from .calculos_empresariales import (
    ActivoDepreciable,
    InsumosBancarizacion,
    InsumosComparacionPatrimonial,
    PagoIndividual,
    PerdidaCompensable,
    calcular_depreciacion,
)
from .modelos import (
    DeduccionImputacion,
    CifrasEscenario,
    EscenarioLeer,
    EscenariosLeer,
    CERO,
    CategoriaDepreciacion,
    Cedula,
    DatosDepreciacion,
    DatosDepreciacionGuardar,
    DatosDepreciacionLeer,
    PagoEfectivo,
    PagoEfectivoCrear,
    PagoEfectivoLeer,
    PerdidaFiscal,
    PerdidaFiscalCrear,
    PerdidaFiscalLeer,
    TipoRentaPerdida,
    ClasificacionIngreso,
    CupoAporte,
    ClasificacionIngresoDatos,
    DeduccionSolicitada,
    DeduccionSolicitadaCrear,
    HojaLiquidacion,
    HojaLiquidacionActualizar,
    IngresoClasificadoLeer,
    LiquidacionLeer,
    ParametrosAplicadosLeer,
    RenglonLeer,
    SimulacionAporteLeer,
    VentaInmueble,
    VentaInmuebleCrear,
    VentaInmuebleLeer,
)
from core.excepciones import DatosVentaInvalidosError, VentaNoEncontradaError


def _dec(valor) -> Decimal:
    """float -> Decimal vía str, para no heredar el error binario."""
    if valor is None:
        return CERO
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


# Parámetros


def obtener_parametros(anio_gravable: int) -> ParametrosAnuales:
    parametros = PARAMETROS_POR_ANIO.get(anio_gravable)
    if parametros is None:
        disponibles = ", ".join(str(a) for a in ANIOS_SOPORTADOS)
        raise AnioGravableNoSoportadoError(
            f"No hay parámetros tributarios cargados para el año gravable "
            f"{anio_gravable} (disponibles: {disponibles}). Agréguelos en "
            f"modulos/parametros/tablas_oficiales.py con su fuente legal antes "
            f"de liquidar: liquidar con los parámetros de otro año produciría "
            f"cifras equivocadas."
        )
    return parametros


# Hoja de liquidación


def obtener_hoja(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> HojaLiquidacion:
    """Hoja del periodo; la crea vacía si no existe."""
    obtener_contribuyente(session, contador_id, contribuyente_id)
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    hoja = session.get(HojaLiquidacion, periodo.id)
    if hoja is None:
        hoja = HojaLiquidacion(
            periodo_fiscal_id=periodo.id, contribuyente_id=contribuyente_id
        )
        session.add(hoja)
        session.commit()
        session.refresh(hoja)
    return hoja


def actualizar_hoja(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: HojaLiquidacionActualizar,
) -> HojaLiquidacion:
    hoja = obtener_hoja(session, contador_id, contribuyente_id, periodo_fiscal_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(hoja, campo, valor)
    hoja.actualizado_en = datetime.now(timezone.utc)
    hoja.actualizado_por_contador_id = contador_id
    session.add(hoja)
    session.commit()
    session.refresh(hoja)
    return hoja


# Deducciones solicitadas


def listar_deducciones(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[DeduccionSolicitada]:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    return list(
        session.exec(
            select(DeduccionSolicitada)
            .where(DeduccionSolicitada.periodo_fiscal_id == periodo.id)
            .order_by(DeduccionSolicitada.id)
        ).all()
    )


def crear_deduccion(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: DeduccionSolicitadaCrear,
) -> DeduccionSolicitada:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    deduccion = DeduccionSolicitada(**datos.model_dump(), periodo_fiscal_id=periodo.id)
    session.add(deduccion)
    session.commit()
    session.refresh(deduccion)
    return deduccion


def imputar_deduccion(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    deduccion_id: int,
    datos: DeduccionImputacion,
) -> DeduccionSolicitada:
    """Fija columna y fila del 210 de una deducción."""
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    deduccion = session.get(DeduccionSolicitada, deduccion_id)
    if deduccion is None or deduccion.periodo_fiscal_id != periodo.id:
        raise DeduccionNoEncontradaError(f"No existe la deducción {deduccion_id}")
    deduccion.subcedula = datos.subcedula.value if datos.subcedula else None
    deduccion.fila_formulario = datos.fila_formulario.value
    session.add(deduccion)
    session.commit()
    session.refresh(deduccion)
    return deduccion


def eliminar_deduccion(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    deduccion_id: int,
) -> None:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    deduccion = session.get(DeduccionSolicitada, deduccion_id)
    if deduccion is None or deduccion.periodo_fiscal_id != periodo.id:
        raise DeduccionNoEncontradaError(
            f"No existe la deducción {deduccion_id} en este periodo"
        )
    session.delete(deduccion)
    session.commit()


# Clasificación de ingresos por cédula


def listar_ingresos_clasificados(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[IngresoClasificadoLeer]:
    """Fuentes de ingreso con su cédula, guardada o sugerida (origen_clasificacion)."""
    fuentes = listar_fuentes_ingreso(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    guardadas = {
        c.fuente_ingreso_id: c.cedula
        for c in session.exec(
            select(ClasificacionIngreso).where(
                ClasificacionIngreso.periodo_fiscal_id == periodo_fiscal_id
            )
        ).all()
    }
    salida = []
    for fuente in fuentes:
        manual = fuente.id in guardadas
        salida.append(
            IngresoClasificadoLeer(
                fuente_ingreso_id=fuente.id,
                concepto=fuente.concepto,
                valor_anual=_dec(fuente.valor_anual),
                retencion_fuente=_dec(fuente.retencion_fuente),
                cedula=guardadas[fuente.id] if manual else clasificador.sugerir_cedula(fuente.concepto),
                origen_clasificacion="MANUAL" if manual else "SUGERIDA",
            )
        )
    return salida


def guardar_clasificaciones(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: List[ClasificacionIngresoDatos],
) -> List[IngresoClasificadoLeer]:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    validas = {
        f.id
        for f in listar_fuentes_ingreso(
            session, contador_id, contribuyente_id, periodo.id
        )
    }
    for item in datos:
        if item.fuente_ingreso_id not in validas:
            raise FuenteIngresoNoEncontradaError(
                f"La fuente de ingreso {item.fuente_ingreso_id} no pertenece a "
                f"este contribuyente y periodo"
            )
        session.merge(
            ClasificacionIngreso(
                fuente_ingreso_id=item.fuente_ingreso_id,
                periodo_fiscal_id=periodo.id,
                cedula=item.cedula,
            )
        )
    session.commit()
    return listar_ingresos_clasificados(
        session, contador_id, contribuyente_id, periodo.id
    )


# Insumos y liquidación


def _agrupar_por_cedula(
    ingresos: List[IngresoClasificadoLeer],
) -> Tuple[Dict[Cedula, Decimal], Decimal, List[IngresoClasificadoLeer]]:
    totales: Dict[Cedula, Decimal] = {c: CERO for c in Cedula}
    retenciones = CERO
    sin_clasificar: List[IngresoClasificadoLeer] = []
    for ingreso in ingresos:
        totales[ingreso.cedula] += ingreso.valor_anual
        if ingreso.cedula == Cedula.SIN_CLASIFICAR:
            sin_clasificar.append(ingreso)
            continue
        if ingreso.cedula != Cedula.EXCLUIDO:
            # Retenciones de pensiones, dividendos y GO vienen de la hoja; no sumar aquí.
            retenciones += ingreso.retencion_fuente
    return totales, retenciones, sin_clasificar


def _resultado_venta(v: VentaInmueble, anio_gravable: int):
    from . import venta_inmuebles

    parametros = obtener_parametros(anio_gravable)
    return venta_inmuebles.calcular(venta_inmuebles.VentaInmueble(
        descripcion=v.descripcion, tipo=v.tipo.value,
        fecha_adquisicion=v.fecha_adquisicion, fecha_venta=v.fecha_venta,
        valor_venta=_dec(v.valor_venta), costo_adquisicion=_dec(v.costo_adquisicion),
        mejoras_y_valorizacion=_dec(v.mejoras_y_valorizacion),
        avaluo_catastral_anterior=(_dec(v.avaluo_catastral_anterior)
                                   if v.avaluo_catastral_anterior is not None else None),
        es_casa_de_habitacion=v.es_casa_de_habitacion,
        porcentaje_participacion=_dec(v.porcentaje_participacion),
        retencion=_dec(v.retencion),
        factor_manual=_dec(v.factor_manual) if v.factor_manual else None,
    ), anio_gravable, parametros.uvt)


def _sumar_ventas_de_inmuebles(
    session: Session, periodo: PeriodoFiscal, insumos: "motor.InsumosLiquidacion"
) -> None:
    """Suma cada venta de inmueble: >= 2 años a GO, < 2 años a no laborales.

    En GO la pérdida no se resta de otras ganancias: costo limitado al valor de venta.
    """
    ventas = session.exec(select(VentaInmueble).where(
        VentaInmueble.periodo_fiscal_id == periodo.id).order_by(VentaInmueble.id)).all()
    for i, v in enumerate(ventas, 1):
        r = _resultado_venta(v, periodo.anio_gravable)
        venta = _dec(v.valor_venta)
        if r.es_ganancia_ocasional:
            go = insumos.ganancias_ocasionales
            go.ingresos += venta
            go.costos += min(r.costo_fiscal, venta)
            go.ganancia_exenta += r.exenta
            go.retenciones += _dec(v.retencion)
            prefijo = "GO-VENTA"
        else:
            insumos.no_laborales.ingresos_brutos += venta
            insumos.no_laborales.costos_y_gastos += r.costo_fiscal
            insumos.retenciones_en_la_fuente += _dec(v.retencion)
            prefijo = "CG-VENTA"
        insumos.renglones_informativos.append(motor.Renglon(
            f"{prefijo}-{i}", f"Venta: {v.descripcion}", r.utilidad if r.utilidad else -r.perdida,
            r.formula, r.fuente))
        insumos.diagnosticos_adicionales.extend(
            f"{v.descripcion}: {aviso}" for aviso in r.avisos)


def construir_insumos(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> Tuple[motor.InsumosLiquidacion, List[IngresoClasificadoLeer]]:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    hoja = obtener_hoja(session, contador_id, contribuyente_id, periodo.id)

    ingresos = listar_ingresos_clasificados(
        session, contador_id, contribuyente_id, periodo.id
    )
    totales, retenciones, sin_clasificar = _agrupar_por_cedula(ingresos)

    activos = listar_activos(session, contador_id, contribuyente_id, periodo.id)
    patrimonio_bruto = sum((_dec(a.valor) for a in activos), CERO)

    deducciones = listar_deducciones(
        session, contador_id, contribuyente_id, periodo.id
    )

    # Costo de ventas (kardex, método de costeo de cada producto).
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    costo_de_ventas = CERO
    if contribuyente.tipo_contribuyente in TIPOS_CON_INVENTARIO:
        costo_de_ventas = _dec(
            calcular_costo_ventas(
                session, contador_id, contribuyente_id, periodo.id
            ).total_costo_ventas
        )

    # Depreciación
    depreciables = [
        ActivoDepreciable(
            descripcion=activo.descripcion,
            costo_fiscal=_dec(activo.valor),
            categoria=datos.categoria.value,
            vida_util_anios=datos.vida_util_anios,
            valor_residual=_dec(datos.valor_residual),
            meses_en_el_periodo=datos.meses_en_el_periodo,
            depreciacion_acumulada=_dec(datos.depreciacion_acumulada),
        )
        for activo, datos in _activos_depreciables(
            session, contador_id, contribuyente_id, periodo.id
        )
    ]

    # Pérdidas compensables
    perdidas = [
        PerdidaCompensable(
            anio_origen=p.anio_origen,
            tipo_renta=p.tipo_renta.value,
            valor_disponible=_dec(p.valor) - _dec(p.valor_compensado),
        )
        for p in session.exec(
            select(PerdidaFiscal).where(
                PerdidaFiscal.contribuyente_id == contribuyente_id
            )
        ).all()
        if _dec(p.valor) - _dec(p.valor_compensado) > CERO
    ]

    # Bancarización
    pagos_individuales = [
        PagoIndividual(descripcion=pago.descripcion, valor=_dec(pago.valor))
        for pago in session.exec(
            select(PagoEfectivo).where(PagoEfectivo.periodo_fiscal_id == periodo.id)
        ).all()
    ]

    # Patrimonio líquido del año anterior. El campo manual tiene prioridad.
    patrimonio_anterior = _dec(hoja.patrimonio_liquido_anterior_manual) if (
        hoja.patrimonio_liquido_anterior_manual is not None
    ) else _patrimonio_liquido_anterior(
        session, contador_id, contribuyente_id, periodo.anio_gravable
    )

    insumos = motor.InsumosLiquidacion(
        anio_gravable=periodo.anio_gravable,
        trabajo=motor.RentasDeTrabajo(
            ingresos_brutos=totales[Cedula.TRABAJO],
            aportes_obligatorios_salud=_dec(hoja.aportes_obligatorios_salud),
            aportes_obligatorios_pension=_dec(hoja.aportes_obligatorios_pension),
            otros_ingresos_no_constitutivos=_dec(hoja.otros_ingresos_no_constitutivos),
            ingresos_sin_vinculo_laboral=totales[Cedula.TRABAJO_SIN_VINCULO],
            costos_y_gastos_sin_vinculo_laboral=_dec(
                hoja.costos_y_gastos_sin_vinculo_laboral
            ),
            opta_por_costos_y_gastos=bool(hoja.opta_por_costos_y_gastos),
        ),
        capital=motor.RentasPorSubcedula(
            ingresos_brutos=totales[Cedula.CAPITAL],
            ingresos_no_constitutivos=_dec(hoja.ingresos_no_constitutivos_capital),
            costos_y_gastos=_dec(hoja.costos_y_gastos_capital),
        ),
        no_laborales=motor.RentasPorSubcedula(
            ingresos_brutos=totales[Cedula.NO_LABORAL],
            devoluciones=_dec(hoja.devoluciones_no_laborales),
            ingresos_no_constitutivos=_dec(hoja.ingresos_no_constitutivos_no_laborales),
            costos_y_gastos=_dec(hoja.costos_y_gastos_no_laborales),
            costo_de_ventas=costo_de_ventas,
        ),
        pensiones=motor.Pensiones(
            ingresos_brutos=_dec(hoja.ingresos_pensiones),
            ingresos_no_constitutivos=_dec(hoja.incrngo_pensiones),
            meses_causados=hoja.meses_pension_causados,
        ),
        dividendos=motor.Dividendos(
            no_gravados=_dec(hoja.dividendos_no_gravados),
            gravados=_dec(hoja.dividendos_gravados),
            retencion_practicada=_dec(hoja.retencion_dividendos),
        ),
        ganancias_ocasionales=motor.GananciasOcasionales(
            ingresos=_dec(hoja.go_ingresos),
            costos=_dec(hoja.go_costos),
            ganancia_exenta=_dec(hoja.go_ganancia_exenta),
            loterias_rifas_apuestas=_dec(hoja.go_loterias_rifas_apuestas),
            retenciones=_dec(hoja.go_retenciones),
        ),
        patrimonio=motor.Patrimonio(
            patrimonio_bruto=patrimonio_bruto, deudas=_dec(hoja.deudas)
        ),
        conceptos_depuracion=[
            motor.ConceptoDepuracion(
                nombre=d.nombre,
                valor=_dec(d.valor),
                sujeto_a_limite_general=d.sujeto_a_limite_general,
                fuente_legal=d.fuente_legal,
                codigo_tope=d.codigo_plantilla,
                subcedula=d.subcedula or None,
                tipo=_fila_de(d),
            )
            for d in deducciones
        ],
        numero_dependientes=hoja.numero_dependientes,
        compras_con_factura_electronica=_dec(hoja.compras_con_factura_electronica),
        renta_presuntiva=_dec(hoja.renta_presuntiva),
        retenciones_en_la_fuente=retenciones,
        otros_descuentos_tributarios=_dec(hoja.otros_descuentos_tributarios),
        anticipo_pagado_anio_anterior=_dec(hoja.anticipo_pagado_anio_anterior),
        saldo_a_favor_anio_anterior=_dec(hoja.saldo_a_favor_anio_anterior),
        anios_declarando=hoja.anios_declarando,
        activos_depreciables=depreciables,
        cedula_depreciacion=hoja.cedula_depreciacion.value,
        perdidas_compensables=perdidas,
        bancarizacion=InsumosBancarizacion(
            total_pagos_del_anio=_dec(hoja.total_pagos_del_anio),
            pagos_en_efectivo=_dec(hoja.pagos_en_efectivo),
            operaciones_individuales_en_efectivo=pagos_individuales,
        ),
        comparacion_patrimonial=InsumosComparacionPatrimonial(
            patrimonio_liquido_anterior=patrimonio_anterior,
            impuestos_pagados_en_el_anio=_dec(hoja.impuestos_pagados_en_el_anio),
            justificaciones=_dec(hoja.justificaciones_patrimoniales),
            aceptar_como_renta_gravable=bool(
                hoja.aceptar_renta_comparacion_patrimonial
            ),
        ),
        metodo_anticipo=hoja.metodo_anticipo.value,
        impuesto_neto_anio_anterior=_dec(hoja.impuesto_neto_anio_anterior),
    )
    _sumar_ventas_de_inmuebles(session, periodo, insumos)
    return insumos, sin_clasificar


def _patrimonio_liquido_anterior(
    session: Session, contador_id: int, contribuyente_id: int, anio_gravable: int
) -> Optional[Decimal]:
    """Patrimonio líquido del año anterior: casilla 31 declarada o, si no hay,
    activos − deudas registrados ese año.
    """
    from ..gestion.servicios import declaracion_vigente

    declarada = declaracion_vigente(session, contribuyente_id, anio_gravable - 1)
    if declarada is not None and "31" in (declarada.casillas or {}):
        return Decimal(declarada.casillas["31"])
    anterior = session.exec(
        select(PeriodoFiscal).where(
            PeriodoFiscal.contribuyente_id == contribuyente_id,
            PeriodoFiscal.anio_gravable == anio_gravable - 1,
        )
    ).first()
    if anterior is None:
        return None
    activos = listar_activos(session, contador_id, contribuyente_id, anterior.id)
    if not activos:
        return None
    bruto = sum((_dec(a.valor) for a in activos), CERO)
    hoja = session.get(HojaLiquidacion, anterior.id)
    deudas = _dec(hoja.deudas) if hoja is not None else CERO
    return bruto - deudas


# Casillas de ingresos brutos (todas las cédulas y GO).
_CASILLAS_DE_INGRESOS = (32, 43, 58, 74, 99, 104, 107, 108, 109, 112)


def _sancion_por_extemporaneidad(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo: PeriodoFiscal,
    resultado: motor.Liquidacion,
    hoy: Optional[date] = None,
) -> Tuple[sanciones.ResultadoSancion, List[str]]:
    """Sanción del art. 641: hasta la presentación o, si está vencida, hasta hoy."""
    # Import tardío: dependencia circular con parametros.
    from ..parametros.servicios import calcular_vencimiento, hoy_colombia

    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    vencimiento = calcular_vencimiento(
        session,
        contribuyente.rut,
        periodo.anio_gravable,
        periodo.fecha_vencimiento_manual,
        periodo.fecha_presentacion,
    )
    if vencimiento.fecha is None:
        return sanciones.ResultadoSancion(), []

    presentada = periodo.fecha_presentacion is not None
    corte = periodo.fecha_presentacion or hoy or hoy_colombia()
    if corte <= vencimiento.fecha:
        return sanciones.ResultadoSancion(), []

    # UVT del año de presentación, no del gravable (mínima y tope 2.500 UVT).
    avisos: List[str] = []
    parametros_corte = PARAMETROS_POR_ANIO.get(corte.year)
    if parametros_corte is None:
        parametros_corte = obtener_parametros(periodo.anio_gravable)
        avisos.append(
            f"No hay UVT cargada para {corte.year}; la sanción mínima y sus topes se "
            f"calcularon con la UVT de {periodo.anio_gravable}. Verifíquela."
        )

    casillas = {r.casilla: r.valor for r in resultado.renglones if r.casilla}
    hoja = session.get(HojaLiquidacion, periodo.id)
    reduccion = hoja.reduccion_sancion.value if hoja is not None else "NINGUNA"
    sancion = sanciones.calcular_extemporaneidad(
        vencimiento=vencimiento.fecha,
        presentacion=corte,
        impuesto_a_cargo=casillas.get(129, CERO),
        ingresos_brutos=sum(
            (casillas.get(n, CERO) for n in _CASILLAS_DE_INGRESOS), CERO
        ),
        patrimonio_liquido_anterior=_patrimonio_liquido_anterior(
            session, contador_id, contribuyente_id, periodo.anio_gravable
        ),
        saldo_a_favor=casillas.get(137, CERO),
        uvt=parametros_corte.uvt,
        reduccion=reduccion,
    )
    if sancion.valor > CERO:
        cuando = (
            f"se presentó el {corte.isoformat()}"
            if presentada
            else f"no se ha presentado y hoy es {corte.isoformat()}"
        )
        avisos.insert(
            0,
            f"La declaración venció el {vencimiento.fecha.isoformat()} y {cuando}: "
            f"{sancion.meses} mes(es) o fracción de retardo. Se liquidó una sanción "
            f"por extemporaneidad de {pesos(sancion.valor)} en la casilla 135"
            + ("" if presentada else ", que aumenta con cada mes que pase")
            + ". Los intereses de mora sobre el impuesto no están incluidos: dependen "
            "de la tasa que certifica la Superintendencia Financiera cada mes."
            + (
                " Si el contribuyente no ha presentado tarde en los últimos dos años, "
                "puede aplicar la reducción del art. 640 ET."
                if reduccion == "NINGUNA"
                else ""
            ),
        )
    return sancion, avisos


def _fila_de(deduccion: DeduccionSolicitada) -> str:
    """Fila del 210 de una deducción.

    Sin campo guardado: la de su plantilla, o "otras deducciones" si es manual.
    """
    if deduccion.fila_formulario:
        return deduccion.fila_formulario
    plantilla = plantillas.obtener(deduccion.codigo_plantilla or "")
    return plantilla.fila if plantilla else motor.DEDUCCION_OTRA


def liquidar_periodo(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> LiquidacionLeer:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    parametros = obtener_parametros(periodo.anio_gravable)
    insumos, sin_clasificar = construir_insumos(
        session, contador_id, contribuyente_id, periodo.id
    )
    resultado = motor.liquidar(insumos, parametros)

    # La sanción depende del impuesto: se liquida, se calcula y se vuelve a
    # liquidar con la casilla 135.
    sancion, avisos_sancion = _sancion_por_extemporaneidad(
        session, contador_id, contribuyente_id, periodo, resultado
    )
    if sancion.valor > CERO:
        insumos.sanciones = sancion.valor
        insumos.formula_sanciones = sancion.formula
        resultado = motor.liquidar(insumos, parametros)

    diagnosticos = avisos_sancion + list(resultado.diagnosticos)
    if sin_clasificar:
        total = sum((i.valor_anual for i in sin_clasificar), CERO)
        diagnosticos.insert(
            0,
            f"{len(sin_clasificar)} fuente(s) de ingreso por {pesos(total)} quedaron sin "
            f"clasificar y NO entraron en la liquidación. Asígneles una cédula "
            f"para que el borrador esté completo.",
        )

    return LiquidacionLeer(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo.id,
        anio_gravable=periodo.anio_gravable,
        parametros=ParametrosAplicadosLeer(
            anio_gravable=parametros.anio_gravable,
            regimen=parametros.regimen,
            uvt=parametros.uvt,
            fuente_uvt=parametros.fuente_uvt,
            fuente_tabla_renta=parametros.fuente_tabla_renta,
            limite_general_porcentaje=parametros.limite_general.porcentaje,
            limite_general_tope_uvt=parametros.limite_general.tope_uvt,
            fuente_limite_general=parametros.limite_general.fuente_legal,
        ),
        renglones=[
            RenglonLeer(
                codigo=r.codigo,
                nombre=r.nombre,
                valor=r.valor,
                valor_declarable=r.valor_declarable,
                formula=r.formula,
                fuente_legal=r.fuente_legal,
                casilla=r.casilla,
            )
            for r in resultado.renglones
        ],
        diagnosticos=diagnosticos,
        notas=resultado.notas,
        casillas_marcadas=resultado.casillas_marcadas,
        ingresos_sin_clasificar=sin_clasificar,
    )


# Escenarios


def _cifras(liq: motor.Liquidacion) -> CifrasEscenario:
    return CifrasEscenario(
        impuesto=liq.valor("IMP-NETO"),
        anticipo=liq.valor("ANTICIPO-SIGUIENTE"),
        saldo_a_pagar=liq.valor("SALDO-A-PAGAR"),
        saldo_a_favor=liq.valor("SALDO-A-FAVOR"),
    )


def _cupo_limite_general(base, parametros) -> Tuple[Decimal, Decimal, Decimal]:
    """Techo, usado y cupo restante del límite del art. 336 num. 3.

    El techo es el menor entre el porcentaje de los ingresos depurados y el
    tope en UVT. Lo que no está sujeto al límite (dependientes y el 1 % de
    compras, art. 336 num. 5) se descuenta de lo usado: ocupa renglón pero no
    ocupa cupo.
    """
    limite = parametros.limite_general
    techo = min(
        base.valor("CG-BASE-LIMITE") * (limite.porcentaje or CERO),
        (limite.tope_uvt or CERO) * parametros.uvt,
    )
    sin_limite = sum(
        (r.valor for r in base.renglones if r.codigo.startswith("CG-NOLIM-")), CERO
    )
    usado = base.valor("CG-EXENTAS-LIMITADAS") - sin_limite
    return techo, usado, (techo - usado).quantize(Decimal("1"))


def _cupo_ahorro_previsional(base, parametros) -> Tuple[Decimal, Decimal, str]:
    """Techo y fuente legal del tope propio de AFC y pensión voluntaria.

    Son el 30 % del ingreso del año y 3.800 UVT, compartidos entre los dos
    conceptos (arts. 126-1 y 126-4 ET). Manda el menor.

    El tope sale de la tabla de parámetros versionada por año, la misma que
    usa el portal para validar los adicionales; acá se aplica además el
    porcentaje sobre el ingreso, que el portal no puede aplicar porque en ese
    momento no conoce el ingreso del periodo.
    """
    tope = parametros.topes_deducciones.get("AHORRO_AFC")
    if tope is None or tope.tope_uvt is None:
        return CERO, CERO, "Sin tope registrado para el año"
    por_uvt = tope.tope_uvt * parametros.uvt
    # Ojo con el nombre del renglón: `Liquidacion.valor()` devuelve cero
    # cuando el código no existe, así que un error de tipeo acá no falla,
    # apaga el techo del porcentaje sin decir nada.
    # `test_el_tope_del_30_por_ciento_del_ingreso_si_aplica` lo vigila.
    ingresos = base.valor("CG-INGRESOS")
    if tope.porcentaje_de_ingresos is not None and ingresos > CERO:
        techo = min(por_uvt, ingresos * tope.porcentaje_de_ingresos)
    else:
        techo = por_uvt
    return redondear_pesos(techo), ingresos, tope.fuente_legal


def simular_aporte_voluntario(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    valor: Decimal,
) -> SimulacionAporteLeer:
    """Reliquida agregando un aporte a AFC o pensión voluntaria. No guarda nada.

    Dos límites recortan el aporte y manda el menor: el general del art. 336
    num. 3 (40 % de los ingresos depurados, tope 1.340 UVT) y el propio de
    estos conceptos (30 % del ingreso, tope 3.800 UVT, compartido entre AFC y
    pensión voluntaria).

    Se devuelve el aporte propuesto y el deducible por separado, y se dice
    cuál de los dos límites recortó. Mostrar el ahorro de un aporte que la ley
    no deja deducir completo sería un consejo equivocado con apariencia de
    cálculo.
    """
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    parametros = obtener_parametros(periodo.anio_gravable)
    insumos, _ = construir_insumos(session, contador_id, contribuyente_id, periodo.id)
    base = motor.liquidar(insumos, parametros)

    techo_general, usado_general, cupo_general = _cupo_limite_general(base, parametros)
    techo_propio, _ingresos, fuente_propio = _cupo_ahorro_previsional(base, parametros)

    # Lo que ya se aportó a estos conceptos ocupa su propio tope.
    usado_propio = sum(
        (
            c.valor
            for c in insumos.conceptos_depuracion
            if c.tipo == motor.EXENTA_AFC
        ),
        CERO,
    )
    cupo_propio = max(techo_propio - usado_propio, CERO)

    deducible = min(valor, max(cupo_general, CERO), cupo_propio)
    motivo = None
    if deducible < valor:
        motivo = (
            "LIMITE_GENERAL"
            if max(cupo_general, CERO) <= cupo_propio
            else "TOPE_PROPIO"
        )

    con_aporte = base
    if deducible > CERO:
        adicional = motor.ConceptoDepuracion(
            nombre="Simulación: aporte voluntario",
            valor=deducible,
            sujeto_a_limite_general=True,
            fuente_legal="Arts. 126-1 y 126-4 ET",
            tipo=motor.EXENTA_AFC,
        )
        con_aporte = motor.liquidar(
            replace(
                insumos,
                conceptos_depuracion=[*insumos.conceptos_depuracion, adicional],
            ),
            parametros,
        )

    a, b = _cifras(base), _cifras(con_aporte)
    advertencias = [
        "Es una simulación: no modifica nada de lo guardado.",
        "El aporte tiene que haberse hecho dentro del año gravable para que "
        "cuente en esta declaración.",
        "Los retiros de un AFC o de pensión voluntaria sin cumplir las "
        "condiciones de permanencia de los arts. 126-1 y 126-4 ET obligan a "
        "devolver el beneficio.",
    ]
    if base.valor("CG-RENTA-LIQUIDA") <= CERO:
        advertencias.append(
            "La renta líquida de la cédula general ya es cero: un aporte no "
            "baja más el impuesto de esta cédula."
        )

    return SimulacionAporteLeer(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo.id,
        anio_gravable=periodo.anio_gravable,
        valor_propuesto=redondear_pesos(valor),
        valor_deducible=redondear_pesos(deducible),
        recortado=deducible < valor,
        motivo_recorte=motivo,
        limite_general=CupoAporte(
            disponible=redondear_pesos(max(cupo_general, CERO)),
            techo=redondear_pesos(techo_general),
            usado=redondear_pesos(usado_general),
            fuente_legal="Art. 336 num. 3 ET",
        ),
        tope_propio=CupoAporte(
            disponible=redondear_pesos(cupo_propio),
            techo=redondear_pesos(techo_propio),
            usado=redondear_pesos(usado_propio),
            fuente_legal=fuente_propio,
        ),
        actual=a,
        con_aporte=b,
        ahorro_en_impuesto=a.impuesto - b.impuesto,
        ahorro_en_saldo=(a.saldo_a_pagar - a.saldo_a_favor)
        - (b.saldo_a_pagar - b.saldo_a_favor),
        advertencias=advertencias,
    )


def _escenario(clave, titulo, actual_txt, alterna_txt, base, alterna, explicacion):
    a, b = _cifras(base), _cifras(alterna)
    return EscenarioLeer(
        clave=clave, titulo=titulo, opcion_actual=actual_txt, opcion_alterna=alterna_txt,
        actual=a, alterna=b,
        ahorro_en_impuesto=a.impuesto - b.impuesto,
        ahorro_en_saldo=(a.saldo_a_pagar - a.saldo_a_favor)
        - (b.saldo_a_pagar - b.saldo_a_favor),
        explicacion=explicacion,
    )


def simular_escenarios(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> EscenariosLeer:
    """Liquida variando una decisión del contribuyente a la vez. No guarda nada."""
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    parametros = obtener_parametros(periodo.anio_gravable)
    insumos, _ = construir_insumos(session, contador_id, contribuyente_id, periodo.id)
    base = motor.liquidar(insumos, parametros)
    escenarios: List[EscenarioLeer] = []

    # Honorarios: costos y gastos o exenta del 25 %
    trabajo = insumos.trabajo
    if (
        trabajo.ingresos_sin_vinculo_laboral > CERO
        and trabajo.costos_y_gastos_sin_vinculo_laboral > CERO
    ):
        alterna = motor.liquidar(
            replace(insumos, trabajo=replace(
                trabajo, opta_por_costos_y_gastos=not trabajo.opta_por_costos_y_gastos
            )),
            parametros,
        )
        con_costos = "Restar costos y gastos de los honorarios"
        con_exenta = "Tomar la renta exenta del 25 %"
        actual_txt, alterna_txt = (
            (con_costos, con_exenta) if trabajo.opta_por_costos_y_gastos
            else (con_exenta, con_costos)
        )
        escenarios.append(_escenario(
            "HONORARIOS", "Honorarios: costos y gastos o renta exenta",
            actual_txt, alterna_txt, base, alterna,
            "El art. 336 num. 4 ET deja escoger a quien recibe honorarios o "
            "compensaciones por servicios personales: o resta los costos y gastos "
            "procedentes, o toma la renta exenta del 25 % del art. 206 num. 10. No "
            "se pueden tomar las dos. Restar costos exige tenerlos soportados y, si "
            "superan el 60 % del ingreso, marcar la casilla 140.",
        ))

    # Anticipo: directo o promedio
    if insumos.anios_declarando > 1 and insumos.impuesto_neto_anio_anterior > CERO:
        actual_metodo = (insumos.metodo_anticipo or "DIRECTO").upper()
        nombres = {
            "DIRECTO": "Sobre el impuesto neto de este año",
            "PROMEDIO": "Sobre el promedio de los dos últimos años",
            "MENOR": "El que resulte menor",
        }
        otro = "PROMEDIO" if actual_metodo == "DIRECTO" else "DIRECTO"
        alterna = motor.liquidar(replace(insumos, metodo_anticipo=otro), parametros)
        escenarios.append(_escenario(
            "ANTICIPO", "Anticipo del año siguiente",
            nombres.get(actual_metodo, actual_metodo), nombres[otro], base, alterna,
            "El art. 807 ET permite calcular el anticipo sobre el impuesto neto del "
            "año o sobre el promedio de los dos últimos, a elección del "
            "contribuyente. No cambia el impuesto: cambia cuánto se paga ahora a "
            "cuenta del año siguiente.",
        ))

    # Cupo sin usar del límite del num. 3
    limite = parametros.limite_general
    techo, usado, cupo = _cupo_limite_general(base, parametros)
    if cupo > CERO and base.valor("CG-RENTA-LIQUIDA") > CERO:
        adicional = motor.ConceptoDepuracion(
            nombre="Simulación: cupo restante del art. 336",
            valor=cupo,
            sujeto_a_limite_general=True,
            fuente_legal="Art. 336 num. 3 ET",
            tipo=motor.EXENTA_AFC,
        )
        alterna = motor.liquidar(
            replace(insumos, conceptos_depuracion=[*insumos.conceptos_depuracion, adicional]),
            parametros,
        )
        escenarios.append(_escenario(
            "CUPO_336", "Cupo sin usar de rentas exentas y deducciones",
            f"Se usan {pesos(usado)} de un cupo de {pesos(techo)}",
            f"Usar los {pesos(cupo)} restantes",
            base, alterna,
            f"El art. 336 num. 3 ET admite rentas exentas y deducciones hasta el "
            f"{motor.porcentaje(limite.porcentaje or CERO)} % de los ingresos "
            f"depurados, sin pasar de {limite.tope_uvt} UVT. Quedan {pesos(cupo)} sin "
            f"usar. La cifra es el máximo teórico: lo usual para ocuparlo son aportes "
            f"voluntarios a pensión o a cuentas AFC, que además tienen su propio "
            f"tope (30 % del ingreso y 3.800 UVT) y deben haberse hecho dentro del "
            f"año gravable. Si la renta exenta del 25 % aplica, baja al aumentar las "
            f"deducciones, y el cálculo ya lo tiene en cuenta.",
        ))

    return EscenariosLeer(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo.id,
        anio_gravable=periodo.anio_gravable,
        escenarios=escenarios,
    )


# Depreciación


def guardar_depreciacion(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: List[DatosDepreciacionGuardar],
) -> List[DatosDepreciacionLeer]:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    validos = {
        a.id for a in listar_activos(session, contador_id, contribuyente_id, periodo.id)
    }
    for item in datos:
        if item.activo_id not in validos:
            raise ActivoNoEncontradoError(
                f"El activo {item.activo_id} no pertenece a este contribuyente y periodo"
            )
        session.merge(
            DatosDepreciacion(
                **item.model_dump(), periodo_fiscal_id=periodo.id
            )
        )
    session.commit()
    return listar_depreciacion(session, contador_id, contribuyente_id, periodo.id)


def eliminar_depreciacion(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    activo_id: int,
) -> None:
    obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    datos = session.get(DatosDepreciacion, activo_id)
    if datos is None or datos.periodo_fiscal_id != periodo_fiscal_id:
        raise ActivoNoEncontradoError(
            f"El activo {activo_id} no tiene datos de depreciación en este periodo"
        )
    session.delete(datos)
    session.commit()


def _activos_depreciables(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[Tuple[Activo, DatosDepreciacion]]:
    activos = {
        a.id: a
        for a in listar_activos(session, contador_id, contribuyente_id, periodo_fiscal_id)
    }
    filas = session.exec(
        select(DatosDepreciacion).where(
            DatosDepreciacion.periodo_fiscal_id == periodo_fiscal_id
        )
    ).all()
    return [(activos[f.activo_id], f) for f in filas if f.activo_id in activos]


def listar_depreciacion(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[DatosDepreciacionLeer]:
    """Activos depreciables y su deducción del año (art. 137, calculada en el motor)."""
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    parametros = obtener_parametros(periodo.anio_gravable)
    pares = _activos_depreciables(session, contador_id, contribuyente_id, periodo.id)

    entradas = [
        ActivoDepreciable(
            descripcion=activo.descripcion,
            costo_fiscal=_dec(activo.valor),
            categoria=datos.categoria.value,
            vida_util_anios=datos.vida_util_anios,
            valor_residual=_dec(datos.valor_residual),
            meses_en_el_periodo=datos.meses_en_el_periodo,
            depreciacion_acumulada=_dec(datos.depreciacion_acumulada),
        )
        for activo, datos in pares
    ]
    calculo = calcular_depreciacion(entradas, parametros)
    por_descripcion = {d[0]: (d[1], d[2]) for d in calculo.detalle}

    salida = []
    for (activo, datos), entrada in zip(pares, entradas):
        valor, formula = por_descripcion.get(activo.descripcion, (CERO, ""))
        salida.append(
            DatosDepreciacionLeer(
                activo_id=activo.id,
                periodo_fiscal_id=periodo.id,
                descripcion=activo.descripcion,
                costo_fiscal=_dec(activo.valor),
                categoria=datos.categoria,
                vida_util_anios=datos.vida_util_anios,
                valor_residual=_dec(datos.valor_residual),
                depreciacion_acumulada=_dec(datos.depreciacion_acumulada),
                meses_en_el_periodo=datos.meses_en_el_periodo,
                tasa_maxima_art_137=parametros.tasas_depreciacion[datos.categoria.value],
                depreciacion_del_periodo=valor,
                formula=formula,
            )
        )
    return salida


def categorias_depreciacion(anio_gravable: int) -> List[dict]:
    """Catálogo del art. 137 con tasas."""
    parametros = obtener_parametros(anio_gravable)
    etiquetas = {
        c.value: c.value.replace("_Y_", " y ").replace("_", " ").capitalize()
        for c in CategoriaDepreciacion
    }
    return [
        {
            "valor": clave,
            "etiqueta": etiquetas[clave],
            "tasa_maxima_anual": tasa,
            "vida_util_equivalente_anios": (Decimal(1) / tasa).quantize(Decimal("0.1")),
        }
        for clave, tasa in parametros.tasas_depreciacion.items()
    ]


# Pérdidas fiscales


def listar_perdidas(
    session: Session, contador_id: int, contribuyente_id: int, anio_gravable: int
) -> List[PerdidaFiscalLeer]:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    parametros = obtener_parametros(anio_gravable)
    limite = anio_gravable - parametros.anios_compensacion_perdidas
    perdidas = session.exec(
        select(PerdidaFiscal)
        .where(PerdidaFiscal.contribuyente_id == contribuyente_id)
        .order_by(PerdidaFiscal.anio_origen)
    ).all()
    return [
        PerdidaFiscalLeer(
            **p.model_dump(),
            saldo_por_compensar=_dec(p.valor) - _dec(p.valor_compensado),
            vigente=p.anio_origen >= limite,
        )
        for p in perdidas
    ]


def crear_perdida(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    datos: PerdidaFiscalCrear,
) -> PerdidaFiscal:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    perdida = PerdidaFiscal(**datos.model_dump(), contribuyente_id=contribuyente_id)
    session.add(perdida)
    session.commit()
    session.refresh(perdida)
    return perdida


def eliminar_perdida(
    session: Session, contador_id: int, contribuyente_id: int, perdida_id: int
) -> None:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    perdida = session.get(PerdidaFiscal, perdida_id)
    if perdida is None or perdida.contribuyente_id != contribuyente_id:
        raise PerdidaNoEncontradaError(f"No existe la pérdida {perdida_id}")
    session.delete(perdida)
    session.commit()


# Pagos en efectivo


def listar_pagos_efectivo(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[PagoEfectivoLeer]:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    parametros = obtener_parametros(periodo.anio_gravable)
    tope = parametros.bancarizacion.limite_individual_uvt * parametros.uvt
    pagos = session.exec(
        select(PagoEfectivo)
        .where(PagoEfectivo.periodo_fiscal_id == periodo.id)
        .order_by(PagoEfectivo.id)
    ).all()
    return [
        PagoEfectivoLeer(**p.model_dump(), supera_limite_individual=_dec(p.valor) > tope)
        for p in pagos
    ]


def crear_pago_efectivo(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    datos: PagoEfectivoCrear,
) -> PagoEfectivo:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    pago = PagoEfectivo(**datos.model_dump(), periodo_fiscal_id=periodo.id)
    session.add(pago)
    session.commit()
    session.refresh(pago)
    return pago


def eliminar_pago_efectivo(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    pago_id: int,
) -> None:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    pago = session.get(PagoEfectivo, pago_id)
    if pago is None or pago.periodo_fiscal_id != periodo.id:
        raise PagoEfectivoNoEncontradoError(f"No existe el pago {pago_id} en este periodo")
    session.delete(pago)
    session.commit()


# Facilidades


def catalogo_plantillas(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[dict]:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    return plantillas.catalogo(obtener_parametros(periodo.anio_gravable).uvt)


def crear_deduccion_desde_plantilla(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    codigo: str,
    valor: Decimal,
) -> DeduccionSolicitada:
    """Crea una deducción desde el catálogo, con su norma."""
    plantilla = plantillas.obtener(codigo)
    if plantilla is None:
        disponibles = ", ".join(p.codigo for p in plantillas.PLANTILLAS)
        raise PlantillaNoEncontradaError(
            f"No existe la plantilla «{codigo}». Disponibles: {disponibles}"
        )
    if codigo in plantillas.CODIGOS_CALCULADOS_POR_EL_MOTOR:
        raise PlantillaNoEncontradaError(
            f"«{plantilla.nombre}» la calcula el motor a partir de la hoja de "
            f"liquidación. Agregarla aquí la contaría dos veces."
        )
    return crear_deduccion(
        session,
        contador_id,
        contribuyente_id,
        periodo_fiscal_id,
        DeduccionSolicitadaCrear(
            nombre=plantilla.nombre,
            valor=valor,
            sujeto_a_limite_general=plantilla.sujeto_a_limite_general,
            fuente_legal=plantilla.fuente_legal,
            codigo_plantilla=plantilla.codigo,
            subcedula=plantilla.subcedula_sugerida,
            fila_formulario=plantilla.fila,
        ),
    )


# Campos del periodo: no se copian al año siguiente.
_NO_SE_COPIAN = {
    "periodo_fiscal_id", "contribuyente_id", "actualizado_en",
    "actualizado_por_contador_id", "impuesto_neto_anio_anterior",
    "total_pagos_del_anio", "pagos_en_efectivo", "patrimonio_liquido_anterior_manual",
    "impuestos_pagados_en_el_anio", "justificaciones_patrimoniales",
    "aceptar_renta_comparacion_patrimonial", "ingresos_pensiones",
    "incrngo_pensiones", "dividendos_no_gravados", "dividendos_gravados",
    "retencion_dividendos", "go_ingresos", "go_costos", "go_ganancia_exenta",
    "go_loterias_rifas_apuestas", "go_retenciones", "renta_presuntiva",
    "otros_descuentos_tributarios", "anticipo_pagado_anio_anterior",
    "saldo_a_favor_anio_anterior", "deudas", "aportes_obligatorios_salud",
    "aportes_obligatorios_pension", "otros_ingresos_no_constitutivos",
    "compras_con_factura_electronica", "costos_y_gastos_sin_vinculo_laboral",
    "ingresos_no_constitutivos_capital", "costos_y_gastos_capital",
    "ingresos_no_constitutivos_no_laborales", "devoluciones_no_laborales",
    "costos_y_gastos_no_laborales", "reduccion_sancion",
}


_PREFIJO_PERDIDA = "CG-PERDIDA-EJERCICIO-"


def _arrastrar_perdidas(
    session: Session, contribuyente_id: int, anio_origen: int, liquidacion: LiquidacionLeer
) -> None:
    """Registra las pérdidas del año anterior como compensables (arts. 147 y 330).

    No sobrescribe una ya registrada del mismo año y tipo.
    """
    tipos_validos = {t.value for t in TipoRentaPerdida}
    for renglon in liquidacion.renglones:
        if not renglon.codigo.startswith(_PREFIJO_PERDIDA) or renglon.valor <= CERO:
            continue
        tipo = renglon.codigo[len(_PREFIJO_PERDIDA):]
        if tipo not in tipos_validos:
            continue
        existente = session.exec(
            select(PerdidaFiscal).where(
                PerdidaFiscal.contribuyente_id == contribuyente_id,
                PerdidaFiscal.anio_origen == anio_origen,
                PerdidaFiscal.tipo_renta == TipoRentaPerdida(tipo),
            )
        ).first()
        if existente is None:
            session.add(
                PerdidaFiscal(
                    contribuyente_id=contribuyente_id,
                    anio_origen=anio_origen,
                    tipo_renta=TipoRentaPerdida(tipo),
                    valor=renglon.valor,
                    nota=f"Arrastrada de la liquidación de {anio_origen}",
                )
            )


def copiar_hoja_del_anio_anterior(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> HojaLiquidacion:
    """Copia del año anterior la situación, no las cifras.

    Se copian: dependientes, método de anticipo, opción de costos, subcédula de
    depreciación. Se traen de la liquidación anterior: impuesto neto (art. 807),
    anticipo (casilla 130) y pérdidas del ejercicio.
    """
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    anterior = session.exec(
        select(PeriodoFiscal).where(
            PeriodoFiscal.contribuyente_id == contribuyente_id,
            PeriodoFiscal.anio_gravable == periodo.anio_gravable - 1,
        )
    ).first()
    if anterior is None:
        raise SinPeriodoAnteriorError(
            f"No hay un periodo {periodo.anio_gravable - 1} registrado para copiar"
        )
    # Crear la hoja destino antes de leer la anterior: obtener_hoja hace commit
    # y el commit expira los objetos cargados.
    hoja = obtener_hoja(session, contador_id, contribuyente_id, periodo.id)

    hoja_anterior = session.get(HojaLiquidacion, anterior.id)
    if hoja_anterior is None:
        raise SinPeriodoAnteriorError(
            f"El periodo {anterior.anio_gravable} no tiene hoja de liquidación"
        )

    for campo, valor in hoja_anterior.model_dump().items():
        if campo not in _NO_SE_COPIAN:
            setattr(hoja, campo, valor)

    # Impuesto neto del año anterior: de su liquidación.
    try:
        liquidacion_anterior = liquidar_periodo(
            session, contador_id, contribuyente_id, anterior.id
        )
        hoja.impuesto_neto_anio_anterior = next(
            (r.valor for r in liquidacion_anterior.renglones if r.codigo == "IMP-NETO"),
            CERO,
        )
        # Casilla 133 del año anterior = casilla 130 de este. El saldo a favor no se
        # arrastra: pudo pedirse en devolución.
        hoja.anticipo_pagado_anio_anterior = next(
            (r.valor_declarable for r in liquidacion_anterior.renglones
             if r.codigo == "ANTICIPO-SIGUIENTE"),
            CERO,
        )
        _arrastrar_perdidas(
            session, contribuyente_id, anterior.anio_gravable, liquidacion_anterior
        )
    except AnioGravableNoSoportadoError:
        pass

    hoja.actualizado_en = datetime.now(timezone.utc)
    hoja.actualizado_por_contador_id = contador_id
    session.add(hoja)
    session.commit()
    session.refresh(hoja)
    return hoja



# Venta de inmuebles


def _leer_venta(v: VentaInmueble, anio_gravable: int) -> VentaInmuebleLeer:
    r = _resultado_venta(v, anio_gravable)
    return VentaInmuebleLeer(
        **v.model_dump(), es_ganancia_ocasional=r.es_ganancia_ocasional, factor=r.factor,
        costo_reajustado=r.costo_reajustado, costo_fiscal=r.costo_fiscal,
        metodo_costo=r.metodo_costo, utilidad=r.utilidad, perdida=r.perdida,
        exenta=r.exenta, formula=r.formula, avisos=r.avisos)


def listar_ventas_inmuebles(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[VentaInmuebleLeer]:
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    ventas = session.exec(select(VentaInmueble).where(
        VentaInmueble.periodo_fiscal_id == periodo_fiscal_id).order_by(VentaInmueble.id)).all()
    return [_leer_venta(v, periodo.anio_gravable) for v in ventas]


def crear_venta_inmueble(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int,
    datos: VentaInmuebleCrear,
) -> VentaInmuebleLeer:
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    if datos.fecha_venta < datos.fecha_adquisicion:
        raise DatosVentaInvalidosError("La fecha de venta es anterior a la de adquisición.")
    if datos.fecha_venta.year != periodo.anio_gravable:
        raise DatosVentaInvalidosError(
            f"La venta es de {datos.fecha_venta.year}: se declara en ese año gravable, "
            f"no en {periodo.anio_gravable}.")
    venta = VentaInmueble(**datos.model_dump(), periodo_fiscal_id=periodo_fiscal_id)
    session.add(venta)
    session.commit()
    session.refresh(venta)
    return _leer_venta(venta, periodo.anio_gravable)


def eliminar_venta_inmueble(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int,
    venta_id: int,
) -> None:
    obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    venta = session.get(VentaInmueble, venta_id)
    if venta is None or venta.periodo_fiscal_id != periodo_fiscal_id:
        raise VentaNoEncontradaError(f"No existe la venta {venta_id} en este periodo")
    session.delete(venta)
    session.commit()
