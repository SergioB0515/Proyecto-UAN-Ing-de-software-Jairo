import re
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlmodel import Session, delete, select

from core.excepciones import (
    AnioGravableNoSoportadoError,
    CalendarioInvalidoError,
    CalendarioOficialNoDisponibleError,
    UmbralNoConfiguradoError,
)

from ..contribuyentes.servicios import obtener_periodo_fiscal
from ..exogena.modelos import TopeExogena
from ..exogena.servicios import obtener_reporte_mas_reciente
from .calendario_oficial import CALENDARIOS_OFICIALES
from .tablas_oficiales import ANIOS_SOPORTADOS, PARAMETROS_POR_ANIO
from .modelos import (
    DetalleCriterio,
    EstadoVencimiento,
    PlazoDeclaracion,
    PlazoDeclaracionDatos,
    VencimientoDeclaracion,
    ResultadoObligacion,
    UmbralDeclaracion,
    UmbralDeclaracionCrear,
)


def registrar_umbral(
    session: Session, datos: UmbralDeclaracionCrear
) -> UmbralDeclaracion:
    umbral = UmbralDeclaracion(**datos.model_dump())
    umbral = session.merge(umbral)
    session.commit()
    session.refresh(umbral)
    return umbral


def cargar_umbral_oficial(session: Session, anio_gravable: int) -> UmbralDeclaracion:
    """Carga los topes para declarar del año desde la tabla oficial.

    Mismo patrón que `cargar_calendario_oficial`: los topes los fija la ley
    (arts. 592 y 594-3 ET), no son una preferencia del contador, así que no
    deberían teclearse a mano. El endpoint de umbrales sigue disponible para
    sobrescribirlos si una norma cambia antes de que salga una versión nueva.
    """
    parametros = PARAMETROS_POR_ANIO.get(anio_gravable)
    if parametros is None:
        disponibles = ", ".join(str(a) for a in ANIOS_SOPORTADOS)
        raise AnioGravableNoSoportadoError(
            f"La aplicación no trae los topes oficiales de {anio_gravable} "
            f"(disponibles: {disponibles}); regístralos a mano"
        )
    topes = parametros.topes_declarar_uvt
    return registrar_umbral(
        session,
        UmbralDeclaracionCrear(
            anio_gravable=anio_gravable,
            valor_uvt=float(parametros.uvt),
            tope_ingresos_uvt=float(topes["ingresos_brutos"]),
            tope_patrimonio_uvt=float(topes["patrimonio_bruto"]),
            tope_consumo_tc_uvt=float(topes["consumos_tarjeta_credito"]),
            tope_compras_uvt=float(topes["compras_y_consumos"]),
            tope_movimiento_uvt=float(topes["consignaciones_y_depositos"]),
        ),
    )


def obtener_umbral_vigente(session: Session, anio_gravable: int) -> UmbralDeclaracion:
    umbral = session.get(UmbralDeclaracion, anio_gravable)
    if umbral is None:
        raise UmbralNoConfiguradoError(
            f"No hay UmbralDeclaracion configurado para el año gravable {anio_gravable}"
        )
    return umbral


def listar_umbrales(session: Session) -> List[UmbralDeclaracion]:
    return list(
        session.exec(
            select(UmbralDeclaracion).order_by(UmbralDeclaracion.anio_gravable)
        ).all()
    )


def verificar_obligacion_declarar(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
) -> ResultadoObligacion:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    reporte = obtener_reporte_mas_reciente(session, periodo_fiscal_id)

    topes = session.exec(
        select(TopeExogena).where(TopeExogena.reporte_exogena_id == reporte.id)
    ).all()

    umbral = obtener_umbral_vigente(session, periodo.anio_gravable)

    definiciones = [
        ("ingreso", "Ingresos", umbral.tope_ingresos_uvt),
        ("patrimonio", "Patrimonio", umbral.tope_patrimonio_uvt),
        ("consumo", "Consumo TC", umbral.tope_consumo_tc_uvt),
        ("movimiento", "Movimiento", umbral.tope_movimiento_uvt),
        ("compra", "Compras", umbral.tope_compras_uvt),
    ]

    criterios = []
    for palabra_clave, nombre, tope_uvt in definiciones:
        tope = next(
            (t for t in topes if palabra_clave in t.etiqueta.lower()), None
        )
        valor_reportado = tope.valor if tope is not None else 0.0
        valor_umbral = umbral.valor_uvt * tope_uvt
        criterios.append(
            DetalleCriterio(
                criterio=nombre,
                valor_reportado=valor_reportado,
                umbral=valor_umbral,
                supera_umbral=valor_reportado >= valor_umbral,
            )
        )

    return ResultadoObligacion(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        anio_gravable=periodo.anio_gravable,
        obligado=any(c.supera_umbral for c in criterios),
        criterios=criterios,
    )


ZONA_COLOMBIA = timezone(timedelta(hours=-5))
DIAS_ALERTA = 15


def hoy_colombia() -> date:
    return datetime.now(ZONA_COLOMBIA).date()


def listar_plazos(session: Session, anio_gravable: int) -> List[PlazoDeclaracion]:
    return list(
        session.exec(
            select(PlazoDeclaracion)
            .where(PlazoDeclaracion.anio_gravable == anio_gravable)
            .order_by(PlazoDeclaracion.digitos_desde)
        ).all()
    )


def reemplazar_plazos(
    session: Session, anio_gravable: int, plazos: List[PlazoDeclaracionDatos]
) -> List[PlazoDeclaracion]:
    ordenados = sorted(plazos, key=lambda p: p.digitos_desde)
    for plazo in ordenados:
        if plazo.digitos_desde > plazo.digitos_hasta:
            raise CalendarioInvalidoError(
                f"Rango inválido: {plazo.digitos_desde:02d} a {plazo.digitos_hasta:02d}"
            )
    for anterior, siguiente in zip(ordenados, ordenados[1:]):
        if siguiente.digitos_desde <= anterior.digitos_hasta:
            raise CalendarioInvalidoError(
                f"Los rangos {anterior.digitos_desde:02d}–{anterior.digitos_hasta:02d} y "
                f"{siguiente.digitos_desde:02d}–{siguiente.digitos_hasta:02d} se solapan"
            )

    session.exec(delete(PlazoDeclaracion).where(PlazoDeclaracion.anio_gravable == anio_gravable))
    for plazo in ordenados:
        session.add(PlazoDeclaracion(anio_gravable=anio_gravable, **plazo.model_dump()))
    session.commit()
    return listar_plazos(session, anio_gravable)


def cargar_calendario_oficial(session: Session, anio_gravable: int) -> List[PlazoDeclaracion]:
    oficial = CALENDARIOS_OFICIALES.get(anio_gravable)
    if oficial is None:
        disponibles = ", ".join(str(a) for a in sorted(CALENDARIOS_OFICIALES))
        raise CalendarioOficialNoDisponibleError(
            f"La aplicación no trae el calendario oficial de {anio_gravable} "
            f"(disponibles: {disponibles}); regístralo a mano"
        )
    return reemplazar_plazos(
        session,
        anio_gravable,
        [PlazoDeclaracionDatos(digitos_desde=d, digitos_hasta=h, fecha=f) for d, h, f in oficial],
    )


def ultimos_dos_digitos(rut: str) -> Optional[int]:
    base = rut.split("-")[0]
    digitos = re.sub(r"\D", "", base)
    if len(digitos) < 2:
        return None
    valor = int(digitos[-2:])
    return 100 if valor == 0 else valor


def calcular_vencimiento(
    session: Session,
    rut: str,
    anio_gravable: int,
    fecha_vencimiento_manual: Optional[date],
    fecha_presentacion: Optional[date],
    hoy: Optional[date] = None,
) -> VencimientoDeclaracion:
    hoy = hoy or hoy_colombia()
    digitos = ultimos_dos_digitos(rut)
    texto_digitos = None if digitos is None else f"{digitos % 100:02d}"

    fecha, origen = fecha_vencimiento_manual, "MANUAL" if fecha_vencimiento_manual else None
    if fecha is None and digitos is not None:
        plazo = session.exec(
            select(PlazoDeclaracion).where(
                PlazoDeclaracion.anio_gravable == anio_gravable,
                PlazoDeclaracion.digitos_desde <= digitos,
                PlazoDeclaracion.digitos_hasta >= digitos,
            )
        ).first()
        if plazo is not None:
            fecha, origen = plazo.fecha, "CALENDARIO"

    dias = (fecha - hoy).days if fecha is not None else None
    if fecha_presentacion is not None:
        estado = EstadoVencimiento.PRESENTADA
    elif fecha is None:
        estado = EstadoVencimiento.SIN_FECHA
    elif dias < 0:
        estado = EstadoVencimiento.VENCIDA
    elif dias <= DIAS_ALERTA:
        estado = EstadoVencimiento.PROXIMA
    else:
        estado = EstadoVencimiento.PENDIENTE

    return VencimientoDeclaracion(
        estado=estado,
        fecha=fecha,
        origen=origen,
        ultimos_digitos=texto_digitos,
        dias_restantes=dias,
        fecha_presentacion=fecha_presentacion,
    )
