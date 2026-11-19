"""Carga los datos de demostración.

    python semilla_demo.py              # carga si no existen
    python semilla_demo.py --reiniciar  # borra y vuelve a crear
    python semilla_demo.py --estado     # informa qué hay cargado

Idempotente. Cada contribuyente muestra un estado distinto (ver demo/README.md).
Nombres, NIT y cédulas son ficticios.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zlib
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from sqlmodel import Session, delete, select

from core.config import ALMACEN_ADJUNTOS
from core.seguridad import hashear_contrasena
from database import crear_tablas, engine
from modulos.adjuntos.modelos import Adjunto, CategoriaAdjunto, TipoEntidadAdjunto
from modulos.auditoria.modelos import EventoAuditoria, IntentoAcceso
from modulos.contadores.modelos import Contador
from modulos.contribuyentes.modelos import (
    Activo,
    Contribuyente,
    EstadoPeriodo,
    FuenteIngreso,
    PeriodoFiscal,
    TipoActivo,
    TipoContribuyente,
)
from modulos.conciliacion.modelos import DecisionRenglon
from modulos.exogena.modelos import (
    RegistroExogena,
    ReporteExogena,
    TopeExogena,
)
from modulos.portal.modelos import (
    AutorizacionTratamiento,
    DatoAdicional,
    EnlaceCarga,
    EnlaceCargaCrear,
)
from modulos.inventario.modelos import (
    Categoria,
    ClasificacionIva,
    MetodoCosteo,
    Producto,
)
from modulos.movimientos.modelos import (
    DocumentoSoporte,
    Movimiento,
    Proveedor,
    TipoDocumentoSoporte,
    TipoMovimiento,
    TipoPersona,
)
from modulos.parametros.calendario_oficial import CALENDARIOS_OFICIALES
from modulos.parametros.modelos import PlazoDeclaracion, UmbralDeclaracion
from modulos.reportes.modelos import CierrePeriodo

# Constantes

EMAIL_DEMO = "contador@demo.co"
CONTRASENA_DEMO = "demo1234"
NOMBRE_DEMO = "Contador de demostración"

# Año fijo, no date.today(): la demo debe ser reproducible.
ANIO = 2025
ANIO_ANTERIOR = 2024
FECHA_CORTE_DEMO = date(ANIO + 1, 3, 14)

NIT_DIAN = "800197268"

# Umbrales para declarar, AG 2025.
UMBRALES = {
    ANIO: dict(
        valor_uvt=49_799.0,
        tope_ingresos_uvt=1_400.0,
        tope_patrimonio_uvt=4_500.0,
        tope_consumo_tc_uvt=1_400.0,
        tope_compras_uvt=1_400.0,
        tope_movimiento_uvt=1_400.0,
    ),
}

# El calendario del AG 2025 vence el 2026-10-26; algunas fechas son relativas
# a hoy para que la cartera muestre varios estados.
HOY = date.today()


# Utilidades


def _tope(etiqueta: str, valor: float) -> Tuple[str, float]:
    return (etiqueta, valor)


def _reg(
    nit: str,
    nombre: str,
    detalle: str,
    valor: float,
    uso: Optional[str] = None,
    info: Optional[str] = None,
    concepto: Optional[str] = None,
    auto_reportado: bool = False,
) -> dict:
    """Registro de exógena, como lo deja el importador."""
    renglones = None
    if uso:
        import re

        encontrados = re.findall(r"\bR\d+\b", uso)
        renglones = ", ".join(encontrados) if encontrados else None
    return dict(
        nit_reportante=nit,
        nombre_reportante=nombre,
        detalle=detalle,
        concepto_code=concepto,
        renglones_sugeridos=renglones,
        valor=valor,
        uso_sugerido=uso,
        info_adicional=info,
        es_auto_reportado=auto_reportado,
        es_dian=nit == NIT_DIAN,
    )


_USO_PATRIMONIO_ANTERIOR = (
    "El Tope 2 - Patrimonio, toma el mayor valor entre la suma de variables del "
    "año gravable reportadas en la exógena y el valor de patrimonio bruto "
    "declarado en el año anterior"
)


def _completar_detalle(
    topes: Sequence[Tuple[str, float]], registros: List[dict]
) -> List[dict]:
    """Agrega el detalle que falta para que cada tope cuadre con sus registros."""
    def suma(numero: int) -> float:
        return sum(
            r["valor"] for r in registros
            if (r.get("uso_sugerido") or "").startswith(f"Tope {numero}:")
        )

    # Texto fijo del registro de patrimonio del año anterior.
    for r in registros:
        if "declarado en el año anterior" in r["detalle"]:
            r["uso_sugerido"] = _USO_PATRIMONIO_ANTERIOR

    for etiqueta, valor in topes:
        numero = int(etiqueta.split()[1])
        falta = valor - suma(numero)
        if numero == 1:
            if abs(falta) >= 1:
                raise ValueError(
                    f"{etiqueta} es {valor:,.0f} y sus registros suman "
                    f"{suma(1):,.0f}: en una exógena real son iguales."
                )
            continue
        if numero == 2:
            anterior = next(
                (r for r in registros if "declarado en el año anterior" in r["detalle"]),
                None,
            )
            if falta >= 1 and anterior is None:
                registros.append(_reg(
                    "", "", "Total patrimonio bruto declarado en el año anterior",
                    valor, _USO_PATRIMONIO_ANTERIOR, auto_reportado=True,
                ))
            elif falta >= 1:
                anterior["valor"] = valor
            continue
        if falta < 1:
            continue
        if numero == 3:
            registros.append(_reg(
                "890903938", "BANCOLOMBIA S A",
                "Total consumos o gastos con tarjeta Crédito o Débito (Concepto: 1023)",
                falta, "Tope 3: Consumos TC", "Clase de Tarjeta: *1* Crédito",
                concepto="1023",
            ))
        elif numero == 4:
            registros.append(_reg(
                "890903938", "BANCOLOMBIA S A",
                "Valor total de los movimientos en cuentas corrientes y de ahorros  "
                "(Titular principal)",
                falta, "Tope 4: Consignaciones e inversiones",
                "Concepto Códigos Tributaria: *1* Cuenta de ahorro",
            ))
        elif numero == 5:
            registros.append(_reg(
                NIT_DIAN, "DIAN",
                "Suma valor total facturas tras ajustes por notas",
                falta, "Tope 5: Compras registradas en Factura Electrónica",
            ))
    return registros


def _crear_exogena(
    session: Session,
    contribuyente_id: int,
    periodo_id: int,
    nombre_archivo: str,
    topes: Sequence[Tuple[str, float]],
    registros: Iterable[dict],
) -> ReporteExogena:
    registros = _completar_detalle(topes, list(registros))
    reporte = ReporteExogena(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_id,
        nombre_archivo_original=nombre_archivo,
        # La consulta de terceros de la demo se toma como descargada en marzo
        # del año siguiente, igual que la que trae el generador de archivos.
        fecha_corte=FECHA_CORTE_DEMO,
        version=1,
    )
    session.add(reporte)
    session.flush()
    for etiqueta, valor in topes:
        session.add(
            TopeExogena(etiqueta=etiqueta, valor=valor, reporte_exogena_id=reporte.id)
        )
    for registro in registros:
        session.add(RegistroExogena(**registro, reporte_exogena_id=reporte.id))
    session.flush()
    return reporte


def _crear_contribuyente(
    session: Session,
    contador_id: int,
    nombre: str,
    rut: str,
    tipo: TipoContribuyente,
    anios: Sequence[int] = (ANIO,),
    vencimiento_manual: Optional[date] = None,
    fecha_presentacion: Optional[date] = None,
) -> Tuple[Contribuyente, dict]:
    contribuyente = Contribuyente(
        nombre=nombre,
        rut=rut,
        tipo_contribuyente=tipo,
        regimen_tributario="Ordinario",
        contador_id=contador_id,
    )
    session.add(contribuyente)
    session.flush()

    periodos = {}
    for anio in anios:
        periodo = PeriodoFiscal(
            anio_gravable=anio,
            estado=EstadoPeriodo.ABIERTO,
            contribuyente_id=contribuyente.id,
            fecha_vencimiento_manual=vencimiento_manual if anio == ANIO else None,
            fecha_presentacion=fecha_presentacion if anio == ANIO else None,
        )
        session.add(periodo)
        session.flush()
        periodos[anio] = periodo
    return contribuyente, periodos


def _activo(
    session: Session,
    contribuyente_id: int,
    periodo_id: int,
    descripcion: str,
    tipo: TipoActivo,
    valor: float,
    concepto: Optional[str] = None,
    palabra_clave: Optional[str] = None,
) -> Activo:
    activo = Activo(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_id,
        descripcion=descripcion,
        tipo=tipo,
        valor=valor,
        vinculo_codigo_concepto=concepto,
        vinculo_palabra_clave=palabra_clave,
    )
    session.add(activo)
    return activo


def _ingreso(
    session: Session,
    contribuyente_id: int,
    periodo_id: int,
    concepto_texto: str,
    valor: float,
    retencion: float = 0.0,
    concepto: Optional[str] = None,
    palabra_clave: Optional[str] = None,
) -> FuenteIngreso:
    fuente = FuenteIngreso(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_id,
        concepto=concepto_texto,
        valor_anual=valor,
        retencion_fuente=retencion,
        vinculo_codigo_concepto=concepto,
        vinculo_palabra_clave=palabra_clave,
    )
    session.add(fuente)
    return fuente


# Umbrales y calendario


def cargar_parametros(session: Session) -> None:
    for anio, datos in UMBRALES.items():
        session.merge(UmbralDeclaracion(anio_gravable=anio, **datos))

    for anio, plazos in CALENDARIOS_OFICIALES.items():
        existentes = session.exec(
            select(PlazoDeclaracion).where(PlazoDeclaracion.anio_gravable == anio)
        ).first()
        if existentes is not None:
            continue
        for desde, hasta, fecha in plazos:
            session.add(
                PlazoDeclaracion(
                    anio_gravable=anio,
                    digitos_desde=desde,
                    digitos_hasta=hasta,
                    fecha=fecha,
                )
            )
    session.flush()


# Casos


def caso_todo_cuadra(session: Session, contador_id: int) -> None:
    """Asalariada obligada, presentada, conciliación limpia (3 COINCIDE).
    Incluye periodo 2024 para copiar activos entre años.
    """
    contribuyente, periodos = _crear_contribuyente(
        session,
        contador_id,
        "Luz Marina Cifuentes Rojas",
        "52814903-1",
        TipoContribuyente.ASALARIADO,
        anios=(ANIO_ANTERIOR, ANIO),
        fecha_presentacion=date(2026, 8, 12),
    )
    cid = contribuyente.id
    actual = periodos[ANIO].id
    previo = periodos[ANIO_ANTERIOR].id

    # Año anterior: solo patrimonio.
    _activo(session, cid, previo, "Cuenta de ahorros Banco de Bogotá",
            TipoActivo.CUENTA, 15_900_000, concepto="1110")
    _activo(session, cid, previo, "Apartamento Suba, matrícula 50N-20384756",
            TipoActivo.INMUEBLE, 138_000_000, concepto="1476")

    _ingreso(session, cid, actual, "Salario Fundación Santa Fe de Bogotá",
             86_400_000, retencion=10_368_000, concepto="5001")
    _activo(session, cid, actual, "Cuenta de ahorros Banco de Bogotá",
            TipoActivo.CUENTA, 18_500_000, concepto="1110")
    _activo(session, cid, actual, "Apartamento Suba, matrícula 50N-20384756",
            TipoActivo.INMUEBLE, 142_000_000, concepto="1476")

    _crear_exogena(
        session, cid, actual, "exogena_cifuentes_rojas_2025.xlsx",
        topes=[
            _tope("Tope 1 - Ingresos", 86_400_000),
            _tope("Tope 2 - Patrimonio", 160_500_000),
            _tope("Tope 3 - Consumo TC", 12_500_000),
            _tope("Tope 4 - Movimiento", 95_000_000),
            _tope("Tope 5 - Compras", 18_000_000),
        ],
        registros=[
            _reg("860007336", "FUNDACION SANTA FE DE BOGOTA",
                 "Pagos por salarios (Concepto: 5001)", 86_400_000,
                 "Tope 1: Ingresos brutos | R32 Rentas de trabajo",
                 concepto="5001"),
            _reg("860002964", "BANCO DE BOGOTA S A",
                 "Saldo de cuentas de ahorro y corrientes a 31 de diciembre "
                 "(Concepto: 1110)", 18_500_000,
                 "Tope 2: Patrimonio | R29 Patrimonio Bruto", concepto="1110"),
            _reg("899999061", "SECRETARIA DISTRITAL DE HACIENDA",
                 "Valor avalúo catastral (Concepto: 1476)", 142_000_000,
                 "Tope 2: Patrimonio | R29 Patrimonio Bruto",
                 info="Matrícula: 50N-20384756 | Participación: 100.00",
                 concepto="1476"),
            # Filas excluidas del cruce.
            _reg("860007336", "FUNDACION SANTA FE DE BOGOTA",
                 "Retención en la fuente practicada por salarios", 10_368_000,
                 "R132 Retenciones año gravable a declarar"),
            _reg("52814903", "LUZ MARINA CIFUENTES ROJAS",
                 "Total patrimonio bruto declarado en el año anterior",
                 153_900_000, auto_reportado=True),
            _reg(NIT_DIAN, "U.A.E. DIRECCION DE IMPUESTOS Y ADUANAS NACIONALES",
                 "Suma valor total facturas tras ajustes por notas", 18_000_000,
                 "Tope 5: Compras registradas en Factura Electrónica"),
        ],
    )


def caso_diferencia_tolerada(session: Session, contador_id: int) -> None:
    """Diferencia de $80.000 dentro de la tolerancia y un vehículo no reportado."""
    contribuyente, periodos = _crear_contribuyente(
        session, contador_id,
        "Héctor Fabio Quintero Pardo", "79548112-4",
        TipoContribuyente.ASALARIADO,
        vencimiento_manual=HOY + timedelta(days=45),
    )
    cid, periodo = contribuyente.id, periodos[ANIO].id

    _ingreso(session, cid, periodo, "Salario Alpina Productos Alimenticios S.A.",
             72_000_000, retencion=6_840_000, concepto="5001")
    _activo(session, cid, periodo, "Cuenta corriente Bancolombia",
            TipoActivo.CUENTA, 24_000_000, concepto="1110")
    _activo(session, cid, periodo, "Mazda CX-30 2022, placa KGT482",
            TipoActivo.VEHICULO, 78_000_000, palabra_clave="vehículo")

    _crear_exogena(
        session, cid, periodo, "exogena_quintero_pardo_2025.xlsx",
        topes=[
            _tope("Tope 1 - Ingresos", 72_000_000),
            _tope("Tope 2 - Patrimonio", 102_080_000),
            _tope("Tope 3 - Consumo TC", 8_900_000),
            _tope("Tope 4 - Movimiento", 41_000_000),
            _tope("Tope 5 - Compras", 9_400_000),
        ],
        registros=[
            _reg("860026665", "ALPINA PRODUCTOS ALIMENTICIOS S A",
                 "Pagos por salarios (Concepto: 5001)", 72_000_000,
                 "Tope 1: Ingresos brutos | R32 Rentas de trabajo",
                 concepto="5001"),
            # Dentro de la tolerancia (0,5 %): COINCIDE.
            _reg("890903938", "BANCOLOMBIA S A",
                 "Saldo de cuentas de ahorro y corrientes a 31 de diciembre "
                 "(Concepto: 1110)", 24_080_000,
                 "Tope 2: Patrimonio | R29 Patrimonio Bruto", concepto="1110"),
            _reg("890903938", "BANCOLOMBIA S A",
                 "Retención en la fuente por rendimientos financieros", 142_000,
                 "R132 Retenciones año gravable a declarar"),
        ],
    )


def caso_ingreso_no_declarado(session: Session, contador_id: int) -> None:
    """Honorarios por $42.300.000 reportados y no declarados, más una discrepancia."""
    contribuyente, periodos = _crear_contribuyente(
        session, contador_id,
        "Diana Carolina Mosquera Luna", "1026587413-2",
        TipoContribuyente.INDEPENDIENTE,
        vencimiento_manual=HOY + timedelta(days=7),
    )
    cid, periodo = contribuyente.id, periodos[ANIO].id

    _ingreso(session, cid, periodo, "Honorarios Consultoría Jurídica Andina S.A.S.",
             54_000_000, retencion=5_940_000, concepto="5004")
    _activo(session, cid, periodo, "Cuenta de ahorros Nequi",
            TipoActivo.CUENTA, 9_200_000, concepto="1110")

    _crear_exogena(
        session, cid, periodo, "exogena_mosquera_luna_2025.xlsx",
        topes=[
            _tope("Tope 1 - Ingresos", 103_800_000),
            _tope("Tope 2 - Patrimonio", 68_000_000),
            _tope("Tope 3 - Consumo TC", 31_400_000),
            _tope("Tope 4 - Movimiento", 118_000_000),
            _tope("Tope 5 - Compras", 22_000_000),
        ],
        registros=[
            # Declaró 54.000.000, el tercero reportó 61.500.000: DISCREPANCIA.
            _reg("900556781", "CONSULTORIA JURIDICA ANDINA S A S",
                 "Honorarios, comisiones y servicios (Concepto: 5004)",
                 61_500_000,
                 "Tope 1: Ingresos brutos | R43 Rentas de trabajo honorarios",
                 concepto="5004"),
            # No declarado: NO_DECLARADO.
            _reg("900778234", "INVERSIONES MEDICAS DEL ORIENTE S A S",
                 "Honorarios, comisiones y servicios (Concepto: 5004)",
                 42_300_000,
                 "Tope 1: Ingresos brutos | R43 Rentas de trabajo honorarios",
                 info="Fecha de la Transacción: 20250930", concepto="5004"),
            _reg("860035827", "BANCO COLPATRIA MULTIBANCA S A",
                 "Saldo de cuentas de ahorro y corrientes a 31 de diciembre "
                 "(Concepto: 1110)", 9_200_000,
                 "Tope 2: Patrimonio | R29 Patrimonio Bruto", concepto="1110"),
            # Consumo con tarjeta: suma al tope, no se marca como no declarado.
            _reg("860035827", "BANCO COLPATRIA MULTIBANCA S A",
                 "Total consumos o gastos con tarjeta Crédito o Débito "
                 "(Concepto: 1023)", 31_400_000, "Tope 3: Consumos TC",
                 concepto="1023"),
            _reg("900556781", "CONSULTORIA JURIDICA ANDINA S A S",
                 "Retención en la fuente practicada por honorarios", 5_940_000,
                 "R132 Retenciones año gravable a declarar"),
        ],
    )


def caso_no_obligado(session: Session, contador_id: int) -> None:
    """Topes bajo el umbral: no obligado."""
    contribuyente, periodos = _crear_contribuyente(
        session, contador_id,
        "Jorge Enrique Lamprea Ávila", "80234119-6",
        TipoContribuyente.ASALARIADO,
        vencimiento_manual=HOY + timedelta(days=60),
    )
    cid, periodo = contribuyente.id, periodos[ANIO].id

    _ingreso(session, cid, periodo, "Salario Ferretería La Campana Ltda.",
             38_000_000, retencion=0, concepto="5001")
    _activo(session, cid, periodo, "Cuenta de ahorros Banco Caja Social",
            TipoActivo.CUENTA, 6_400_000, concepto="1110")

    _crear_exogena(
        session, cid, periodo, "exogena_lamprea_avila_2025.xlsx",
        topes=[
            _tope("Tope 1 - Ingresos", 38_000_000),
            _tope("Tope 2 - Patrimonio", 96_000_000),
            _tope("Tope 3 - Consumo TC", 4_100_000),
            _tope("Tope 4 - Movimiento", 22_500_000),
            _tope("Tope 5 - Compras", 3_800_000),
        ],
        registros=[
            _reg("830114921", "FERRETERIA LA CAMPANA LTDA",
                 "Pagos por salarios (Concepto: 5001)", 38_000_000,
                 "Tope 1: Ingresos brutos | R32 Rentas de trabajo",
                 concepto="5001"),
            _reg("860007335", "BANCO CAJA SOCIAL S A",
                 "Saldo de cuentas de ahorro y corrientes a 31 de diciembre "
                 "(Concepto: 1110)", 6_400_000,
                 "Tope 2: Patrimonio | R29 Patrimonio Bruto", concepto="1110"),
        ],
    )


def caso_con_inventario(session: Session, contador_id: int) -> None:
    """Comerciante con inventario (PEPS y promedio ponderado).
    Vencido, con alerta y periodo ABIERTO para cerrarlo en vivo.
    """
    contribuyente, periodos = _crear_contribuyente(
        session, contador_id,
        "Nelson Andrés Beltrán Gómez", "900845612-7",
        TipoContribuyente.MIXTO,
    )
    cid, periodo = contribuyente.id, periodos[ANIO].id

    _ingreso(session, cid, periodo, "Ventas a Serviteca La Séptima S.A.S.",
             112_400_000, retencion=2_810_000, concepto="5005")
    _ingreso(session, cid, periodo, "Ventas de mostrador (consumidor final)",
             56_300_000, retencion=0, palabra_clave="mostrador")
    _activo(session, cid, periodo, "Cuenta corriente Davivienda",
            TipoActivo.CUENTA, 34_200_000, concepto="1110")
    _activo(session, cid, periodo, "Local comercial Barrio Restrepo",
            TipoActivo.INMUEBLE, 185_000_000, concepto="1476")
    _activo(session, cid, periodo, "Chevrolet N300 2019, placa THS719",
            TipoActivo.VEHICULO, 42_000_000, palabra_clave="vehículo")

    _crear_exogena(
        session, cid, periodo, "exogena_beltran_gomez_2025.xlsx",
        topes=[
            # Suma de terceros: el tope no incluye todas las ventas.
            _tope("Tope 1 - Ingresos", 119_240_000),
            _tope("Tope 2 - Patrimonio", 310_000_000),
            _tope("Tope 3 - Consumo TC", 18_600_000),
            _tope("Tope 4 - Movimiento", 204_000_000),
            _tope("Tope 5 - Compras", 135_950_000),
        ],
        registros=[
            _reg("901234567", "SERVITECA LA SEPTIMA S A S",
                 "Pagos o abonos en cuenta por compras (Concepto: 5005)",
                 112_400_000,
                 "Tope 1: Ingresos brutos | R74 Ingresos brutos rentas no laborales",
                 concepto="5005"),
            _reg("860034313", "BANCO DAVIVIENDA S A",
                 "Saldo de cuentas de ahorro y corrientes a 31 de diciembre "
                 "(Concepto: 1110)", 34_200_000,
                 "Tope 2: Patrimonio | R29 Patrimonio Bruto", concepto="1110"),
            # Avalúo 198,5 M frente a costo fiscal 185 M: DISCREPANCIA a revisar.
            _reg("899999061", "SECRETARIA DISTRITAL DE HACIENDA",
                 "Valor avalúo catastral (Concepto: 1476)", 198_500_000,
                 "Tope 2: Patrimonio | R29 Patrimonio Bruto",
                 info="Matrícula: 50S-40117823 | Participación: 100.00",
                 concepto="1476"),
            # Rendimientos no declarados: NO_DECLARADO.
            _reg("860002503", "SEGUROS BOLIVAR S A",
                 "Rendimientos financieros e intereses (Concepto: 1301)",
                 6_840_000,
                 "Tope 1: Ingresos brutos | R58 Ingresos brutos rentas de capital",
                 concepto="1301"),
            _reg("901234567", "SERVITECA LA SEPTIMA S A S",
                 "Retención en la fuente practicada por compras", 2_810_000,
                 "R132 Retenciones año gravable a declarar"),
        ],
    )

    # Inventario
    repuestos = Categoria(contribuyente_id=cid, nombre="Repuestos",
                          descripcion="Filtros, frenos y partes de motor")
    lubricantes = Categoria(contribuyente_id=cid, nombre="Lubricantes",
                            descripcion="Aceites, refrigerantes y aditivos")
    session.add_all([repuestos, lubricantes])
    session.flush()

    productos = {
        "P-001": Producto(contribuyente_id=cid, codigo="P-001",
                          nombre="Filtro de aceite Mazda 2.0",
                          clasificacion_iva=ClasificacionIva.GRAVADO,
                          metodo_costeo=MetodoCosteo.PEPS,
                          categoria_id=repuestos.id),
        "P-002": Producto(contribuyente_id=cid, codigo="P-002",
                          nombre="Pastillas de freno Toyota Hilux",
                          clasificacion_iva=ClasificacionIva.GRAVADO,
                          metodo_costeo=MetodoCosteo.PEPS,
                          categoria_id=repuestos.id),
        "P-003": Producto(contribuyente_id=cid, codigo="P-003",
                          nombre="Aceite 20W-50 x galón",
                          clasificacion_iva=ClasificacionIva.GRAVADO,
                          metodo_costeo=MetodoCosteo.PROMEDIO_PONDERADO,
                          categoria_id=lubricantes.id),
        "P-004": Producto(contribuyente_id=cid, codigo="P-004",
                          nombre="Refrigerante verde x litro",
                          clasificacion_iva=ClasificacionIva.EXCLUIDO,
                          metodo_costeo=MetodoCosteo.PROMEDIO_PONDERADO,
                          categoria_id=lubricantes.id),
    }
    session.add_all(productos.values())

    distribuidora = Proveedor(contribuyente_id=cid,
                              nombre="Distribuidora Automotriz del Valle S.A.S.",
                              tipo_persona=TipoPersona.JURIDICA,
                              identificacion="900412887")
    progreso = Proveedor(contribuyente_id=cid,
                         nombre="Repuestos El Progreso",
                         tipo_persona=TipoPersona.NATURAL,
                         identificacion="19458223")
    session.add_all([distribuidora, progreso])
    session.flush()

    documentos = {}
    definicion_docs = [
        ("FE-1042", TipoDocumentoSoporte.FACTURA, date(ANIO, 3, 15),
         "Compra de filtros y aceite"),
        ("FE-1188", TipoDocumentoSoporte.FACTURA, date(ANIO, 7, 10),
         "Reposición de filtros"),
        ("FE-1203", TipoDocumentoSoporte.FACTURA, date(ANIO, 4, 2),
         "Compra de pastillas de freno"),
        ("FE-1350", TipoDocumentoSoporte.FACTURA, date(ANIO, 6, 5),
         "Compra de aceite 20W-50"),
        ("DS-0077", TipoDocumentoSoporte.DOCUMENTO_SOPORTE, date(ANIO, 5, 11),
         "Compra a proveedor no obligado a facturar"),
        ("VT-2201", TipoDocumentoSoporte.FACTURA, date(ANIO, 8, 20),
         "Venta Serviteca La Séptima"),
        ("VT-2202", TipoDocumentoSoporte.FACTURA, date(ANIO, 9, 14),
         "Venta Serviteca La Séptima"),
        ("VT-2203", TipoDocumentoSoporte.FACTURA, date(ANIO, 10, 30),
         "Venta mostrador"),
        ("VT-2204", TipoDocumentoSoporte.FACTURA, date(ANIO, 11, 3),
         "Venta mostrador"),
        ("VT-2205", TipoDocumentoSoporte.FACTURA, date(ANIO, 2, 20),
         "Compra inicial de aceite"),
    ]
    for numero, tipo, fecha, descripcion in definicion_docs:
        documento = DocumentoSoporte(contribuyente_id=cid, tipo=tipo,
                                     numero=numero, fecha=fecha,
                                     descripcion=descripcion)
        session.add(documento)
        documentos[numero] = documento
    session.flush()

    # (producto, tipo, documento, proveedor, fecha, cantidad, valor_unitario)
    definicion_movs = [
        ("P-001", TipoMovimiento.ENTRADA, "FE-1042", distribuidora,
         date(ANIO, 3, 15), 400, 28_000),
        ("P-001", TipoMovimiento.ENTRADA, "FE-1188", distribuidora,
         date(ANIO, 7, 10), 300, 31_000),
        ("P-001", TipoMovimiento.SALIDA, "VT-2201", None,
         date(ANIO, 8, 20), 450, 52_000),
        ("P-002", TipoMovimiento.ENTRADA, "FE-1203", progreso,
         date(ANIO, 4, 2), 250, 95_000),
        ("P-002", TipoMovimiento.SALIDA, "VT-2202", None,
         date(ANIO, 9, 14), 180, 165_000),
        ("P-003", TipoMovimiento.ENTRADA, "VT-2205", distribuidora,
         date(ANIO, 2, 20), 600, 72_000),
        ("P-003", TipoMovimiento.ENTRADA, "FE-1350", distribuidora,
         date(ANIO, 6, 5), 500, 78_000),
        ("P-003", TipoMovimiento.SALIDA, "VT-2203", None,
         date(ANIO, 10, 30), 850, 124_000),
        ("P-004", TipoMovimiento.ENTRADA, "DS-0077", progreso,
         date(ANIO, 5, 11), 1000, 9_500),
        ("P-004", TipoMovimiento.SALIDA, "VT-2204", None,
         date(ANIO, 11, 3), 600, 17_000),
    ]
    stock = {codigo: 0.0 for codigo in productos}
    for codigo, tipo, numero, proveedor, fecha, cantidad, unitario in definicion_movs:
        producto = productos[codigo]
        session.add(
            Movimiento(
                contribuyente_id=cid,
                producto_id=producto.id,
                periodo_fiscal_id=periodo,
                documento_soporte_id=documentos[numero].id,
                proveedor_id=proveedor.id if proveedor is not None else None,
                tipo=tipo,
                fecha=fecha,
                cantidad=cantidad,
                valor_unitario=unitario,
            )
        )
        stock[codigo] += cantidad if tipo == TipoMovimiento.ENTRADA else -cantidad

    for codigo, cantidad in stock.items():
        if cantidad < 0:
            raise RuntimeError(
                f"Datos demo inconsistentes: el producto {codigo} queda con "
                f"stock negativo ({cantidad})"
            )
        productos[codigo].stock_actual = cantidad
    session.add_all(productos.values())


def caso_sin_exogena(session: Session, contador_id: int) -> None:
    """Periodo abierto sin exógena, para cargarla en vivo."""
    contribuyente, periodos = _crear_contribuyente(
        session, contador_id,
        "Sandra Milena Osorio Peña", "1015442308-5",
        TipoContribuyente.ASALARIADO,
        vencimiento_manual=HOY + timedelta(days=21),
    )
    cid, periodo = contribuyente.id, periodos[ANIO].id

    _ingreso(session, cid, periodo, "Salario Clínica del Country S.A.",
             64_800_000, retencion=4_536_000, concepto="5001")
    _activo(session, cid, periodo, "Cuenta de ahorros Bancolombia",
            TipoActivo.CUENTA, 11_300_000, concepto="1110")
    _activo(session, cid, periodo, "Renault Logan 2021, placa HQB341",
            TipoActivo.VEHICULO, 46_500_000, palabra_clave="vehículo")


CASOS = (
    caso_todo_cuadra,
    caso_diferencia_tolerada,
    caso_ingreso_no_declarado,
    caso_no_obligado,
    caso_con_inventario,
    caso_sin_exogena,
)


# Adjuntos de demostración. Viven en disco; sin disco persistente se pierden
# al reiniciar, así que se regeneran en cada arranque.

PDF = "application/pdf"
PNG = "image/png"


def _pdf(titulo: str, subtitulo: str, lineas: Sequence[Tuple[str, str]]) -> bytes:
    """PDF de una página tipo certificado."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    lienzo = canvas.Canvas(buffer, pagesize=LETTER)
    ancho, alto = LETTER

    lienzo.setFont("Helvetica-Bold", 15)
    lienzo.drawString(72, alto - 92, titulo)
    lienzo.setFont("Helvetica", 10)
    lienzo.drawString(72, alto - 110, subtitulo)
    lienzo.setFont("Helvetica-Oblique", 8)
    lienzo.drawString(72, alto - 126, "DOCUMENTO DE DEMOSTRACIÓN — datos ficticios")
    lienzo.line(72, alto - 134, ancho - 72, alto - 134)

    y = alto - 168
    for etiqueta, valor in lineas:
        lienzo.setFont("Helvetica", 11)
        lienzo.drawString(72, y, etiqueta)
        lienzo.setFont("Helvetica-Bold", 11)
        lienzo.drawRightString(ancho - 72, y, valor)
        y -= 24

    lienzo.showPage()
    lienzo.save()
    return buffer.getvalue()


def _png(ancho: int, alto: int, pintar: Callable[[int, int], Tuple[int, int, int]]) -> bytes:
    """PNG RGB sin Pillow."""
    filas = bytearray()
    for y in range(alto):
        filas.append(0)  # filtro None por línea
        for x in range(ancho):
            filas.extend(pintar(x, y))

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return (
            struct.pack(">I", len(datos))
            + tipo
            + datos
            + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
        )

    cabecera = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", cabecera)
        + trozo(b"IDAT", zlib.compress(bytes(filas), 9))
        + trozo(b"IEND", b"")
    )


def _captura_factura() -> bytes:
    """Imagen tipo factura, para la vista previa."""
    ancho, alto = 620, 380

    def pintar(x: int, y: int) -> Tuple[int, int, int]:
        if y < 56:
            return (37, 60, 92)  # barra de título
        if y < 60:
            return (24, 40, 62)
        if 84 <= y < 104 and 40 <= x < 360:
            return (203, 213, 225)  # encabezado
        if 132 <= y < 300 and 40 <= x < ancho - 40:
            fila = (y - 132) // 28
            if (y - 132) % 28 < 18:
                return (241, 245, 249) if fila % 2 == 0 else (226, 232, 240)
        if 316 <= y < 344 and ancho - 240 <= x < ancho - 40:
            return (191, 219, 254)  # total
        return (255, 255, 255)

    return _png(ancho, alto, pintar)


def _especificaciones_adjuntos(session: Session, contador_id: int) -> List[dict]:
    """Adjuntos de la demo, con sus entidades."""

    def contribuyente(rut: str) -> Optional[Contribuyente]:
        return session.exec(
            select(Contribuyente).where(
                Contribuyente.contador_id == contador_id, Contribuyente.rut == rut
            )
        ).first()

    especificaciones: List[dict] = []

    luz = contribuyente("52814903-1")
    if luz is not None:
        apartamento = session.exec(
            select(Activo).where(
                Activo.contribuyente_id == luz.id,
                Activo.descripcion.like("Apartamento Suba%"),
            ).order_by(Activo.id.desc())
        ).first()
        if apartamento is not None:
            especificaciones.append(dict(
                contribuyente_id=luz.id,
                entidad_tipo=TipoEntidadAdjunto.ACTIVO,
                entidad_id=apartamento.id,
                periodo_fiscal_id=apartamento.periodo_fiscal_id,
                categoria=CategoriaAdjunto.RECIBO,
                descripcion="Impuesto predial del inmueble, soporte del avalúo",
                nombre="impuesto-predial-2025.pdf",
                slug="predial",
                tipo_mime=PDF,
                generar=lambda: _pdf(
                    "Impuesto Predial Unificado 2025",
                    "Secretaría Distrital de Hacienda — Bogotá D.C.",
                    [
                        ("Matrícula inmobiliaria", "50N-20384756"),
                        ("Dirección", "Calle 145 # 102-30, Suba"),
                        ("Avalúo catastral", "$ 142.000.000"),
                        ("Impuesto liquidado", "$ 923.000"),
                        ("Estado", "Pagado"),
                    ],
                ),
            ))

    diana = contribuyente("1026587413-2")
    if diana is not None:
        honorarios = session.exec(
            select(FuenteIngreso).where(
                FuenteIngreso.contribuyente_id == diana.id,
                FuenteIngreso.concepto.like("Honorarios%"),
            )
        ).first()
        if honorarios is not None:
            especificaciones.append(dict(
                contribuyente_id=diana.id,
                entidad_tipo=TipoEntidadAdjunto.FUENTE_INGRESO,
                entidad_id=honorarios.id,
                periodo_fiscal_id=honorarios.periodo_fiscal_id,
                categoria=CategoriaAdjunto.CERTIFICADO,
                descripcion="Certificado del pagador: no coincide con lo declarado",
                nombre="certificado-ingresos-y-retenciones.pdf",
                slug="certificado-honorarios",
                tipo_mime=PDF,
                generar=lambda: _pdf(
                    "Certificado de ingresos y retenciones",
                    "Consultoría Jurídica Andina S.A.S. — NIT 900.556.781",
                    [
                        ("Año gravable", "2025"),
                        ("Concepto", "Honorarios"),
                        ("Valor pagado o abonado", "$ 61.500.000"),
                        ("Retención practicada", "$ 5.940.000"),
                        ("Valor registrado en la aplicación", "$ 54.000.000"),
                    ],
                ),
            ))

    nelson = contribuyente("900845612-7")
    if nelson is not None:
        especificaciones.append(dict(
            contribuyente_id=nelson.id,
            entidad_tipo=TipoEntidadAdjunto.CONTRIBUYENTE,
            entidad_id=nelson.id,
            periodo_fiscal_id=None,
            categoria=CategoriaAdjunto.OTRO,
            descripcion="RUT actualizado del contribuyente",
            nombre="rut-actualizado.pdf",
            slug="rut",
            tipo_mime=PDF,
            generar=lambda: _pdf(
                "Registro Único Tributario",
                "Dirección de Impuestos y Aduanas Nacionales",
                [
                    ("NIT", "900.845.612-7"),
                    ("Razón social", "Nelson Andrés Beltrán Gómez"),
                    ("Actividad económica", "4530 — Comercio de partes para vehículos"),
                    ("Responsabilidades", "05 — Impto. renta régimen ordinario"),
                    ("Fecha de actualización", "2026-01-22"),
                ],
            ),
        ))

        factura = session.exec(
            select(DocumentoSoporte).where(
                DocumentoSoporte.contribuyente_id == nelson.id,
                DocumentoSoporte.numero == "FE-1042",
            )
        ).first()
        if factura is not None:
            especificaciones.append(dict(
                contribuyente_id=nelson.id,
                entidad_tipo=TipoEntidadAdjunto.DOCUMENTO_SOPORTE,
                entidad_id=factura.id,
                periodo_fiscal_id=None,
                categoria=CategoriaAdjunto.FACTURA,
                descripcion="Captura de la factura electrónica del proveedor",
                nombre="factura-fe-1042.png",
                slug="factura-fe-1042",
                tipo_mime=PNG,
                generar=_captura_factura,
            ))

    return especificaciones


def asegurar_adjuntos_demo(session: Session, contador_id: int) -> int:
    """Crea los adjuntos que falten. Devuelve cuántos archivos escribió."""
    base = Path(ALMACEN_ADJUNTOS)
    escritos = 0

    for especificacion in _especificaciones_adjuntos(session, contador_id):
        extension = ".pdf" if especificacion["tipo_mime"] == PDF else ".png"
        ruta_relativa = f"{especificacion['contribuyente_id']}/demo-{especificacion['slug']}{extension}"
        ruta = base / ruta_relativa

        fila = session.exec(
            select(Adjunto).where(
                Adjunto.contribuyente_id == especificacion["contribuyente_id"],
                Adjunto.ruta_relativa == ruta_relativa,
            )
        ).first()
        if fila is not None and ruta.is_file() and ruta.stat().st_size > 0:
            continue

        contenido = especificacion["generar"]()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        escritos += 1

        huella = hashlib.sha256(contenido).hexdigest()
        if fila is None:
            session.add(Adjunto(
                contribuyente_id=especificacion["contribuyente_id"],
                entidad_tipo=especificacion["entidad_tipo"],
                entidad_id=especificacion["entidad_id"],
                periodo_fiscal_id=especificacion["periodo_fiscal_id"],
                categoria=especificacion["categoria"],
                descripcion=especificacion["descripcion"],
                nombre_original=especificacion["nombre"],
                ruta_relativa=ruta_relativa,
                tipo_mime=especificacion["tipo_mime"],
                tamano_bytes=len(contenido),
                sha256=huella,
            ))
        else:
            fila.tamano_bytes = len(contenido)
            fila.sha256 = huella
            session.add(fila)

    if escritos:
        session.commit()
    return escritos


# Carga y borrado


def _contador_demo(session: Session) -> Optional[Contador]:
    return session.exec(select(Contador).where(Contador.email == EMAIL_DEMO)).first()


def borrar_demo(session: Session) -> bool:
    contador = _contador_demo(session)
    if contador is None:
        return False

    ids: List[int] = list(
        session.exec(
            select(Contribuyente.id).where(Contribuyente.contador_id == contador.id)
        ).all()
    )

    if ids:
        # Borrar la fila no borra el archivo.
        base_almacen = Path(ALMACEN_ADJUNTOS)
        for ruta_relativa in session.exec(
            select(Adjunto.ruta_relativa).where(Adjunto.contribuyente_id.in_(ids))
        ).all():
            (base_almacen / ruta_relativa).unlink(missing_ok=True)

        reportes = list(
            session.exec(
                select(ReporteExogena.id).where(
                    ReporteExogena.contribuyente_id.in_(ids)
                )
            ).all()
        )
        if reportes:
            session.exec(
                delete(RegistroExogena).where(
                    RegistroExogena.reporte_exogena_id.in_(reportes)
                )
            )
            session.exec(
                delete(TopeExogena).where(
                    TopeExogena.reporte_exogena_id.in_(reportes)
                )
            )
        # Primero las tablas de liquidación (llaves foráneas).
        from modulos.liquidacion.modelos import (
            ClasificacionIngreso, DatosDepreciacion, DeduccionSolicitada,
            HojaLiquidacion, PagoEfectivo, PerdidaFiscal, VentaInmueble,
        )
        periodos = list(
            session.exec(
                select(PeriodoFiscal.id).where(PeriodoFiscal.contribuyente_id.in_(ids))
            ).all()
        )
        if periodos:
            from modulos.gestion.modelos import (
                DeclaracionPresentada, DocumentoSolicitado, SeguimientoDeclaracion,
            )
            for modelo in (ClasificacionIngreso, DatosDepreciacion, DeduccionSolicitada,
                           PagoEfectivo, HojaLiquidacion, VentaInmueble,
                           DeclaracionPresentada,
                           DocumentoSolicitado, SeguimientoDeclaracion):
                session.exec(delete(modelo).where(modelo.periodo_fiscal_id.in_(periodos)))
        session.exec(delete(PerdidaFiscal).where(PerdidaFiscal.contribuyente_id.in_(ids)))

        # El orden importa: cada modelo va antes del que referencia. Las
        # autorizaciones apuntan a los enlaces, así que van antes.
        for modelo in (
            DecisionRenglon, DatoAdicional,
            AutorizacionTratamiento, EnlaceCarga,
            ReporteExogena, Adjunto, Movimiento, CierrePeriodo, DocumentoSoporte,
            Proveedor, Producto, Categoria, Activo, FuenteIngreso, PeriodoFiscal,
        ):
            session.exec(delete(modelo).where(modelo.contribuyente_id.in_(ids)))
        session.exec(delete(Contribuyente).where(Contribuyente.id.in_(ids)))

    session.exec(
        delete(EventoAuditoria).where(EventoAuditoria.contador_id == contador.id)
    )
    session.exec(delete(IntentoAcceso).where(IntentoAcceso.email == EMAIL_DEMO))
    session.delete(contador)
    session.commit()
    return True


def gestion_demo(session: Session, contador_id: int) -> None:
    """Gestión en tres estados.

    - Luz Marina: presentada a tiempo, proceso completo.
    - Diana: recogiendo documentos, a una semana del plazo.
    - Nelson: vencido sin presentar; sanción e intereses.
    Noviembre de 2026 queda sin tasa para mostrar el aviso.
    """
    from modulos.gestion import servicios as gestion
    from modulos.gestion.modelos import (
        DeclaracionAnteriorRegistrar, DocumentoActualizar, EstadoDocumento,
        PresentacionRegistrar, SeguimientoActualizar,
    )

    def ubicar(rut: str) -> Tuple[int, int]:
        c = session.exec(select(Contribuyente).where(
            Contribuyente.contador_id == contador_id, Contribuyente.rut == rut)).one()
        p = session.exec(select(PeriodoFiscal).where(
            PeriodoFiscal.contribuyente_id == c.id,
            PeriodoFiscal.anio_gravable == ANIO)).one()
        return c.id, p.id

    def marcar_documentos(cid: int, pid: int, cuantos: Optional[int] = None) -> None:
        docs = gestion.solicitud_documentos(session, contador_id, cid, pid).documentos
        for d in docs[:cuantos]:
            gestion.actualizar_documento(session, contador_id, cid, pid, d.clave,
                                         DocumentoActualizar(estado=EstadoDocumento.RECIBIDO))

    # Luz Marina
    cid, pid = ubicar("52814903-1")
    gestion.registrar_declaracion_anterior(session, contador_id, cid, DeclaracionAnteriorRegistrar(
        anio_gravable=ANIO_ANTERIOR, fecha_presentacion=date(2025, 8, 14),
        numero_formulario="2104987654321",
        casillas={29: 153_900_000, 30: 0, 31: 153_900_000, 32: 79_200_000,
                  111: 41_300_000, 126: 1_450_000, 132: 9_100_000, 133: 0,
                  136: 0, 137: 0},
    ))
    marcar_documentos(cid, pid)
    gestion.actualizar_seguimiento(session, contador_id, cid, pid, SeguimientoActualizar(
        cruce_revisado_en=date(2026, 8, 3), liquidacion_revisada_en=date(2026, 8, 5),
        aprobada_cliente_en=date(2026, 8, 10)))
    gestion.registrar_presentacion(session, contador_id, cid, pid, PresentacionRegistrar(
        fecha_presentacion=date(2026, 8, 12), numero_formulario="2105123456789"))

    # Diana
    cid, pid = ubicar("1026587413-2")
    marcar_documentos(cid, pid, 2)

    # Nelson
    cid, pid = ubicar("900845612-7")
    marcar_documentos(cid, pid)
    gestion.actualizar_seguimiento(session, contador_id, cid, pid, SeguimientoActualizar(
        cruce_revisado_en=date(2026, 8, 14), liquidacion_revisada_en=date(2026, 8, 18)))


def cargar_demo(session: Session) -> Contador:
    contador = Contador(
        nombre=NOMBRE_DEMO,
        email=EMAIL_DEMO,
        hash_contrasena=hashear_contrasena(CONTRASENA_DEMO),
    )
    session.add(contador)
    session.flush()

    cargar_parametros(session)
    for caso in CASOS:
        caso(session, contador.id)

    session.commit()
    gestion_demo(session, contador.id)
    asegurar_portal_demo(session, contador.id)
    asegurar_adjuntos_demo(session, contador.id)
    return contador


def asegurar_portal_demo(session: Session, contador_id: int) -> int:
    """Deja un enlace de carga vigente por contribuyente, para la demo.

    No hay que generar nada más: la lista de documentos que se le piden al
    cliente se deriva de la exógena y de la hoja cada vez que se consulta, así
    que el portal ya tiene qué mostrar en cuanto el enlace existe.

    Es idempotente, como el resto de la semilla.
    """
    from modulos.portal.servicios import crear_enlace

    creados = 0
    contribuyentes = session.exec(
        select(Contribuyente).where(Contribuyente.contador_id == contador_id)
    ).all()
    for contribuyente in contribuyentes:
        periodos = session.exec(
            select(PeriodoFiscal)
            .where(PeriodoFiscal.contribuyente_id == contribuyente.id)
            .order_by(PeriodoFiscal.anio_gravable)
        ).all()
        if not periodos:
            continue
        periodo = periodos[-1]
        if periodo.estado == EstadoPeriodo.CERRADO:
            continue
        ya_tiene = session.exec(
            select(EnlaceCarga.id).where(
                EnlaceCarga.periodo_fiscal_id == periodo.id,
                EnlaceCarga.revocado_en.is_(None),
            )
        ).first()
        if ya_tiene is None:
            crear_enlace(
                session,
                contador_id,
                contribuyente.id,
                EnlaceCargaCrear(
                    periodo_fiscal_id=periodo.id,
                    dias_vigencia=90,
                    nota="Enlace de la demostración",
                ),
            )
            creados += 1
    session.commit()
    return creados


def informar(session: Session) -> None:
    contador = _contador_demo(session)
    if contador is None:
        print("No hay datos demo cargados.")
        return
    total = len(
        session.exec(
            select(Contribuyente.id).where(Contribuyente.contador_id == contador.id)
        ).all()
    )
    print(f"Datos demo presentes: {contador.email} con {total} contribuyentes.")

    base = Path(ALMACEN_ADJUNTOS)
    rutas = session.exec(
        select(Adjunto.ruta_relativa).where(Adjunto.ruta_relativa.like("%/demo-%"))
    ).all()
    faltantes = [r for r in rutas if not (base / r).is_file()]
    print(f"Soportes adjuntos: {len(rutas)} registrados, {len(faltantes)} sin archivo en disco.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reiniciar", action="store_true",
                        help="borra los datos demo existentes y los vuelve a crear")
    parser.add_argument("--estado", action="store_true",
                        help="solo informa si hay datos demo cargados")
    args = parser.parse_args(argv)

    crear_tablas()

    with Session(engine) as session:
        if args.estado:
            informar(session)
            return 0

        existente = _contador_demo(session)
        if existente is not None:
            if not args.reiniciar:
                reparados = asegurar_adjuntos_demo(session, existente.id)
                print(
                    f"Los datos demo ya existen ({EMAIL_DEMO}). "
                    "Usa --reiniciar para borrarlos y volver a crearlos."
                )
                if reparados:
                    print(f"Se regeneraron {reparados} archivos de soporte que faltaban en disco.")
                return 0
            borrar_demo(session)
            print("Datos demo anteriores borrados.")

        contador = cargar_demo(session)
        total = len(
            session.exec(
                select(Contribuyente.id).where(
                    Contribuyente.contador_id == contador.id
                )
            ).all()
        )

    print("Datos demo cargados.")
    print(f"  Usuario     : {EMAIL_DEMO}")
    print(f"  Contraseña  : {CONTRASENA_DEMO}")
    print(f"  Año gravable: {ANIO}")
    print(f"  Contribuyentes: {total}")
    print("Guion de la demostración en demo/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
