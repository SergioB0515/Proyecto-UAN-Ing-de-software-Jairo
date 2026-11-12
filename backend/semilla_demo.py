"""Carga un conjunto de datos de demostración en la base de datos.

Pensado para mostrar la aplicación funcionando (sustentación, evaluación del
coordinador, despliegue público) sin tener que registrar nada a mano y sin que
la demo dependa de la máquina de quien la presenta.

Uso, desde la carpeta ``backend/`` y con el entorno virtual activo:

    python semilla_demo.py              # carga los datos si no existen
    python semilla_demo.py --reiniciar  # borra los datos demo y los vuelve a crear
    python semilla_demo.py --estado     # solo informa qué hay cargado

Es **idempotente**: si el contador demo ya existe, no duplica nada.

Los seis contribuyentes no son relleno: cada uno existe para enseñar un estado
distinto de la aplicación. Ver ``demo/README.md`` para el guion de la demo.

AVISO SOBRE LAS CIFRAS
----------------------
Los umbrales UVT de ``UMBRALES`` y los códigos de concepto de la exógena son
valores de referencia para la demostración. Antes de usarlos como dato real
hay que contrastarlos con la resolución de la DIAN del año gravable
correspondiente. Las cédulas, NIT, nombres y matrículas son ficticios.
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
from modulos.exogena.modelos import (
    RegistroExogena,
    ReporteExogena,
    TopeExogena,
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

# --------------------------------------------------------------------------
# Constantes de la demo
# --------------------------------------------------------------------------

EMAIL_DEMO = "contador@demo.co"
CONTRASENA_DEMO = "demo1234"
NOMBRE_DEMO = "Contador de demostración"

# Año gravable fijo. NO derivarlo de date.today(): si cambia, los cálculos
# dejan de ser reproducibles y la demo deja de coincidir con las capturas.
ANIO = 2025
ANIO_ANTERIOR = 2024

NIT_DIAN = "800197268"

# Umbrales para estar obligado a declarar renta del año gravable 2025.
# UVT y topes en UVT: verificar contra la resolución vigente de la DIAN.
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

# El calendario oficial del AG 2025 termina el 2026-10-26. Después de esa
# fecha, todo contribuyente sin fecha manual aparece como VENCIDA. Para que el
# panel de cartera muestre varios estados el día de la demo, algunos
# contribuyentes llevan fecha_vencimiento_manual relativa a hoy.
HOY = date.today()


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------


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
    """Un renglón de la exógena, tal como lo dejaría el importador de Excel."""
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
    """Deja la exógena de ejemplo coherente consigo misma, como una real.

    En el archivo de la DIAN cada tope sale de su detalle: es la suma de los
    registros marcados con ese tope, y el de patrimonio es el mayor entre esa
    suma y lo declarado el año anterior. Los casos de la semilla fijan los
    topes a mano para contar una historia, así que aquí se agrega el detalle
    que les falta. Sin esto el cruce con la DIAN, que reconstruye cada tope,
    marcaría los cinco como descuadrados en todos los contribuyentes de la demo.
    """
    def suma(numero: int) -> float:
        return sum(
            r["valor"] for r in registros
            if (r.get("uso_sugerido") or "").startswith(f"Tope {numero}:")
        )

    # El registro de patrimonio del año anterior trae siempre este texto.
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


# --------------------------------------------------------------------------
# Parámetros globales (umbrales y calendario)
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Los seis casos
# --------------------------------------------------------------------------


def caso_todo_cuadra(session: Session, contador_id: int) -> None:
    """Asalariada obligada, ya presentó, conciliación limpia (3 COINCIDE).

    Sirve para abrir la demo: así se ve un contribuyente sin pendientes.
    También tiene periodo 2024 con activos, para mostrar «copiar activos
    de otro año».
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

    # Año anterior: solo patrimonio, para la copia de activos entre años.
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
            # Las tres filas siguientes el sistema las excluye del cruce.
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
    """Diferencia de $80.000 que NO se marca como error (está en tolerancia),
    más un vehículo que ningún tercero reportó.

    Sirve para responder «¿y no les saltan alarmas por cualquier peso?».
    """
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
            # $80.000 de diferencia: dentro de la tolerancia (0,5 %), COINCIDE.
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
    """EL caso que justifica la aplicación: un tercero reportó $42.300.000 de
    honorarios que el contribuyente no declaró, más una discrepancia real.

    Es el contribuyente con el que se abre la pantalla de conciliación.
    """
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
            # Declaró 54.000.000; el tercero reportó 61.500.000 -> DISCREPANCIA.
            _reg("900556781", "CONSULTORIA JURIDICA ANDINA S A S",
                 "Honorarios, comisiones y servicios (Concepto: 5004)",
                 61_500_000,
                 "Tope 1: Ingresos brutos | R43 Rentas de trabajo honorarios",
                 concepto="5004"),
            # Nunca lo declaró -> NO_DECLARADO. Este es el hallazgo de la demo.
            _reg("900778234", "INVERSIONES MEDICAS DEL ORIENTE S A S",
                 "Honorarios, comisiones y servicios (Concepto: 5004)",
                 42_300_000,
                 "Tope 1: Ingresos brutos | R43 Rentas de trabajo honorarios",
                 info="Fecha de la Transacción: 20250930", concepto="5004"),
            _reg("860035827", "BANCO COLPATRIA MULTIBANCA S A",
                 "Saldo de cuentas de ahorro y corrientes a 31 de diciembre "
                 "(Concepto: 1110)", 9_200_000,
                 "Tope 2: Patrimonio | R29 Patrimonio Bruto", concepto="1110"),
            # Consumo con tarjeta: alimenta el tope, pero el sistema no lo
            # lista como «no declarado» (no es un ingreso ni un activo).
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
    """Todos los topes por debajo del umbral: el sistema dice «no obligado».

    Sirve para mostrar que la app también ahorra trabajo descartando clientes.
    """
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
    """Comerciante con inventario: categorías, productos, proveedores,
    documentos soporte y movimientos para kardex y costo de ventas.

    Usa los dos métodos de costeo (PEPS y promedio ponderado). Queda VENCIDA y
    con una alerta sin declarar: es la fila roja del panel de cartera.
    El periodo queda ABIERTO para poder demostrar el cierre en vivo.
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
            # La suma de lo que reportan los terceros: el negocio vende más
            # de lo que la exógena alcanza a ver, y eso no infla el tope.
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
            # Avalúo catastral 198,5 M contra costo fiscal declarado 185 M:
            # DISCREPANCIA legítima que el contador debe revisar, no un error.
            _reg("899999061", "SECRETARIA DISTRITAL DE HACIENDA",
                 "Valor avalúo catastral (Concepto: 1476)", 198_500_000,
                 "Tope 2: Patrimonio | R29 Patrimonio Bruto",
                 info="Matrícula: 50S-40117823 | Participación: 100.00",
                 concepto="1476"),
            # Rendimientos nunca declarados -> NO_DECLARADO.
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

    # ---- Inventario -----------------------------------------------------
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
    """Contribuyente con periodo abierto y SIN exógena importada.

    Es el que se usa para cargar el archivo en vivo durante la demo: el panel
    de cartera lo muestra con el aviso «aún no se ha importado la exógena».
    """
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


# --------------------------------------------------------------------------
# Soportes adjuntos de demostración
#
# Los adjuntos se guardan en disco (ALMACEN_ADJUNTOS), no en la base de datos.
# En un despliegue SIN disco persistente —Render en plan Free, por ejemplo— ese
# disco se borra cada vez que el servicio se reinicia o despierta de la
# suspensión, y la pantalla de Soportes quedaría con filas apuntando a archivos
# que ya no existen.
#
# Por eso los archivos se generan aquí en vez de subirse a mano, con una ruta
# fija por adjunto, y `asegurar_adjuntos_demo` los vuelve a crear en cada
# arranque si faltan. Así la demo aguanta un reinicio.
# --------------------------------------------------------------------------

PDF = "application/pdf"
PNG = "image/png"


def _pdf(titulo: str, subtitulo: str, lineas: Sequence[Tuple[str, str]]) -> bytes:
    """Un PDF de una página con aspecto de certificado o recibo."""
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
    """PNG RGB sin dependencias externas (Pillow no está en requirements)."""
    filas = bytearray()
    for y in range(alto):
        filas.append(0)  # filtro «None» de cada línea
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
    """Imagen que simula la captura de una factura, para probar la vista previa."""
    ancho, alto = 620, 380

    def pintar(x: int, y: int) -> Tuple[int, int, int]:
        if y < 56:
            return (37, 60, 92)            # barra de título
        if y < 60:
            return (24, 40, 62)
        if 84 <= y < 104 and 40 <= x < 360:
            return (203, 213, 225)         # «encabezado» del documento
        if 132 <= y < 300 and 40 <= x < ancho - 40:
            fila = (y - 132) // 28
            if (y - 132) % 28 < 18:
                return (241, 245, 249) if fila % 2 == 0 else (226, 232, 240)
        if 316 <= y < 344 and ancho - 240 <= x < ancho - 40:
            return (191, 219, 254)         # «total»
        return (255, 255, 255)

    return _png(ancho, alto, pintar)


def _especificaciones_adjuntos(session: Session, contador_id: int) -> List[dict]:
    """Define qué adjuntos lleva la demo, resolviendo las entidades reales."""

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
    """Crea los adjuntos demo que falten, en la base o en el disco.

    Devuelve cuántos archivos escribió. Es seguro llamarla en cada arranque:
    si todo está en su sitio, no hace nada.
    """
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


# --------------------------------------------------------------------------
# Carga y borrado
# --------------------------------------------------------------------------


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
        # Los adjuntos viven en disco: borrar la fila no borra el archivo.
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
        # Las tablas de la liquidación cuelgan de los periodos y de los
        # activos: se borran antes, o la llave foránea impide borrar lo demás.
        from modulos.liquidacion.modelos import (
            ClasificacionIngreso, DatosDepreciacion, DeduccionSolicitada,
            HojaLiquidacion, PagoEfectivo, PerdidaFiscal,
        )
        periodos = list(
            session.exec(
                select(PeriodoFiscal.id).where(PeriodoFiscal.contribuyente_id.in_(ids))
            ).all()
        )
        if periodos:
            for modelo in (ClasificacionIngreso, DatosDepreciacion, DeduccionSolicitada,
                           PagoEfectivo, HojaLiquidacion):
                session.exec(delete(modelo).where(modelo.periodo_fiscal_id.in_(periodos)))
        session.exec(delete(PerdidaFiscal).where(PerdidaFiscal.contribuyente_id.in_(ids)))

        for modelo in (
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
    asegurar_adjuntos_demo(session, contador.id)
    return contador


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
