"""Orquestación de la liquidación: lee la base, arma los insumos, llama al motor.

Frontera de tipos
-----------------
El resto de la aplicación guarda dinero en `float`. Este módulo lo convierte a
`Decimal` con `_dec()`, que pasa por `str` a propósito: `Decimal(0.1)` arrastra
el error binario del float, `Decimal(str(0.1))` no. Toda conversión ocurre aquí
y nada más abajo vuelve a ver un float.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from core.excepciones import (
    AnioGravableNoSoportadoError,
    DeduccionNoEncontradaError,
    FuenteIngresoNoEncontradaError,
)

from ..contribuyentes.modelos import Activo, FuenteIngreso
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
from . import clasificador, motor
from .modelos import (
    CERO,
    Cedula,
    ClasificacionIngreso,
    ClasificacionIngresoDatos,
    DeduccionSolicitada,
    DeduccionSolicitadaCrear,
    HojaLiquidacion,
    HojaLiquidacionActualizar,
    IngresoClasificadoLeer,
    LiquidacionLeer,
    ParametrosAplicadosLeer,
    RenglonLeer,
)


def _dec(valor) -> Decimal:
    """Convierte a Decimal sin heredar el error de representación del float."""
    if valor is None:
        return CERO
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


# ---------------------------------------------------------------------------
# Parámetros
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Hoja de liquidación
# ---------------------------------------------------------------------------


def obtener_hoja(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> HojaLiquidacion:
    """Devuelve la hoja del periodo, creándola vacía la primera vez.

    Crearla al leer evita que el frontend tenga que distinguir «no existe» de
    «existe en blanco»: la hoja en blanco es un estado válido y liquida en cero.
    """
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


# ---------------------------------------------------------------------------
# Deducciones solicitadas
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Clasificación de ingresos por cédula
# ---------------------------------------------------------------------------


def listar_ingresos_clasificados(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[IngresoClasificadoLeer]:
    """Lista las fuentes de ingreso con su cédula: la guardada, o la sugerida.

    `origen_clasificacion` distingue las dos, para que la interfaz muestre qué
    confirmó el contador y qué sigue siendo una sugerencia del sistema.
    """
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


# ---------------------------------------------------------------------------
# Armado de insumos y liquidación
# ---------------------------------------------------------------------------


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
            # La retención de pensiones, dividendos y ganancias ocasionales se
            # captura en la hoja; sumarla aquí la contaría dos veces.
            retenciones += ingreso.retencion_fuente
    return totales, retenciones, sin_clasificar


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
        capital=motor.RentasPorSubcedula(ingresos_brutos=totales[Cedula.CAPITAL]),
        no_laborales=motor.RentasPorSubcedula(ingresos_brutos=totales[Cedula.NO_LABORAL]),
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
    )
    return insumos, sin_clasificar


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

    diagnosticos = list(resultado.diagnosticos)
    if sin_clasificar:
        total = sum((i.valor_anual for i in sin_clasificar), CERO)
        diagnosticos.insert(
            0,
            f"{len(sin_clasificar)} fuente(s) de ingreso por ${total} quedaron sin "
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
            )
            for r in resultado.renglones
        ],
        diagnosticos=diagnosticos,
        notas=resultado.notas,
        ingresos_sin_clasificar=sin_clasificar,
    )
