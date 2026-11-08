import io
import re
from typing import List, Optional

import pandas as pd
from sqlmodel import Session, select

from core.config import TAMANO_MAXIMO_EXOGENA_MB
from core.excepciones import (
    ArchivoDemasiadoGrandeError,
    ArchivoExogenaInvalidoError,
    PeriodoFiscalCerradoError,
    ReporteExogenaNoEncontradoError,
)

from ..contribuyentes.modelos import EstadoPeriodo
from ..contribuyentes.servicios import obtener_contribuyente, obtener_periodo_fiscal
from .modelos import (
    ConsultanteInfo,
    FilaConError,
    RegistroExogena,
    RegistroExogenaBase,
    ReporteExogena,
    ReporteExogenaImportado,
    ResultadoParseo,
    TopeExogena,
    TopeExogenaBase,
)

PATRON_CONCEPTO = re.compile(r"\(Concepto:\s*(\d+)\)", re.IGNORECASE)

PATRON_RENGLON = re.compile(r"\bR\d+\b")

# La DIAN a veces no asigna el renglón: ofrece un menú de posibilidades y deja
# la decisión al declarante ("Según el bien o derecho reportado se puede usar
# en renglones como ... | R112 ... | R29 ... | R30 ..."). Tomarlos como
# definitivos suma el mismo valor en varios renglones a la vez: la misma plata
# contada como patrimonio, como deuda y como ganancia ocasional.
PATRONES_CONDICIONALES = (
    re.compile(r"se\s+puede(?:n)?\s+usar", re.IGNORECASE),
    re.compile(r"seg[uú]n\s+el\s+(?:bien|tipo|concepto)", re.IGNORECASE),
    re.compile(r"dependiendo\s+de", re.IGNORECASE),
)


def _es_sugerencia_condicional(uso: Optional[str]) -> bool:
    return bool(uso) and any(p.search(uso) for p in PATRONES_CONDICIONALES)

NIT_DIAN = "800197268"

FIRMAS_EXCEL = (b"PK\x03\x04", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
EXTENSIONES_EXCEL = (".xlsx", ".xls")


def leer_archivo_exogena(flujo, nombre: Optional[str]) -> bytes:
    limite = int(TAMANO_MAXIMO_EXOGENA_MB * 1024 * 1024)
    contenido = flujo.read(limite + 1)
    if len(contenido) > limite:
        raise ArchivoDemasiadoGrandeError(
            f"El archivo supera el máximo de {TAMANO_MAXIMO_EXOGENA_MB:g} MB"
        )
    if not (nombre or "").lower().endswith(EXTENSIONES_EXCEL) or not contenido.startswith(FIRMAS_EXCEL):
        raise ArchivoExogenaInvalidoError(
            "El archivo debe ser un Excel (.xlsx o .xls) descargado de la DIAN"
        )
    return contenido


def parsear_archivo_exogena(contenido: bytes) -> ResultadoParseo:
    try:
        tabla = pd.read_excel(io.BytesIO(contenido), header=None)
    except Exception as exc:
        raise ArchivoExogenaInvalidoError(
            "No se pudo leer el archivo como Excel"
        ) from exc

    filas = [[_celda(v) for v in fila] for fila in tabla.values.tolist()]

    indice_encabezado = None
    for i, fila in enumerate(filas):
        if _texto(_col(fila, 0)) == "NIT" and "Nombre" in (
            _texto(_col(fila, 1)) or ""
        ):
            indice_encabezado = i
            break
    if indice_encabezado is None:
        raise ArchivoExogenaInvalidoError(
            'No se encontró la fila de encabezados "NIT" / "Nombre"'
        )

    consultante = ConsultanteInfo()
    for fila in filas[:indice_encabezado]:
        etiqueta = _texto(_col(fila, 0)) or ""
        valor = _texto(_col(fila, 2))
        if etiqueta.startswith("Tipo de documento"):
            consultante.tipo_documento = valor
        elif etiqueta.startswith("Identificación:"):
            consultante.identificacion = valor
        elif etiqueta.startswith("Nombres / Razón social"):
            consultante.nombre = valor

    resultado = ResultadoParseo(consultante=consultante)

    for i in range(indice_encabezado + 1, len(filas)):
        fila = filas[i]
        if all(v is None for v in fila):
            continue

        nit = _texto(_col(fila, 0))
        detalle = _texto(_col(fila, 4))

        if nit is None:
            if detalle and detalle.replace(" ", "").lower().startswith("tope"):
                valor_tope = _col(fila, 5)
                try:
                    valor_tope = float(valor_tope) if valor_tope is not None else 0.0
                except (TypeError, ValueError):
                    valor_tope = 0.0
                resultado.topes.append(
                    TopeExogenaBase(etiqueta=detalle, valor=valor_tope)
                )
            continue

        try:
            valor = float(_col(fila, 5))
            if valor != valor:
                raise ValueError
        except (TypeError, ValueError):
            resultado.errores.append(
                FilaConError(
                    fila=i + 1, motivo="Valor no numérico en la columna Valor"
                )
            )
            continue

        nit = nit.replace(" ", "")
        detalle = detalle or ""
        uso = _texto(_col(fila, 6))
        match_concepto = PATRON_CONCEPTO.search(detalle)
        condicional = _es_sugerencia_condicional(uso)
        renglones = PATRON_RENGLON.findall(uso or "")

        resultado.registros.append(
            RegistroExogenaBase(
                nit_reportante=nit,
                nombre_reportante=_texto(_col(fila, 1)) or "",
                detalle=detalle,
                concepto_code=match_concepto.group(1) if match_concepto else None,
                renglones_sugeridos=", ".join(renglones) if renglones else None,
                renglones_son_condicionales=condicional,
                valor=valor,
                uso_sugerido=uso,
                info_adicional=_texto(_col(fila, 7)),
                es_auto_reportado=nit == consultante.identificacion,
                es_dian=nit == NIT_DIAN,
            )
        )

    return resultado


def _celda(valor):
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    if isinstance(valor, str) and not valor.strip():
        return None
    return valor


def _col(fila, indice):
    return fila[indice] if indice < len(fila) else None


def _texto(valor) -> Optional[str]:
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = str(valor).strip()
    return texto or None


def importar_reporte_exogena(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    periodo_fiscal_id: int,
    contenido: bytes,
    nombre_archivo: str,
) -> ReporteExogenaImportado:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    if periodo.estado == EstadoPeriodo.CERRADO:
        raise PeriodoFiscalCerradoError(
            f"El periodo fiscal {periodo.anio_gravable} está cerrado: no admite "
            "nuevas importaciones de exógena"
        )

    resultado = parsear_archivo_exogena(contenido)

    reporte = ReporteExogena(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo_fiscal_id,
        nombre_archivo_original=nombre_archivo,
    )
    session.add(reporte)
    session.flush()

    for tope in resultado.topes:
        session.add(
            TopeExogena(**tope.model_dump(), reporte_exogena_id=reporte.id)
        )
    for registro in resultado.registros:
        session.add(
            RegistroExogena(**registro.model_dump(), reporte_exogena_id=reporte.id)
        )

    session.commit()
    session.refresh(reporte)
    return ReporteExogenaImportado(
        **reporte.model_dump(),
        consultante=resultado.consultante,
        cantidad_topes=len(resultado.topes),
        cantidad_registros=len(resultado.registros),
        errores=resultado.errores,
    )


def listar_reportes_exogena(
    session: Session, contador_id: int, contribuyente_id: int
) -> List[ReporteExogena]:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    return list(
        session.exec(
            select(ReporteExogena)
            .where(ReporteExogena.contribuyente_id == contribuyente_id)
            .order_by(ReporteExogena.fecha_importacion.desc(), ReporteExogena.id.desc())
        ).all()
    )


def obtener_reporte_exogena(
    session: Session, contador_id: int, contribuyente_id: int, reporte_exogena_id: int
) -> ReporteExogena:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    reporte = session.get(ReporteExogena, reporte_exogena_id)
    if reporte is None or reporte.contribuyente_id != contribuyente_id:
        raise ReporteExogenaNoEncontradoError(
            f"No existe el reporte de exógena {reporte_exogena_id} para el "
            f"contribuyente {contribuyente_id}"
        )
    return reporte


def obtener_reporte_mas_reciente(
    session: Session, periodo_fiscal_id: int
) -> ReporteExogena:
    reporte = session.exec(
        select(ReporteExogena)
        .where(ReporteExogena.periodo_fiscal_id == periodo_fiscal_id)
        .order_by(ReporteExogena.fecha_importacion.desc(), ReporteExogena.id.desc())
    ).first()
    if reporte is None:
        raise ReporteExogenaNoEncontradoError(
            f"No se ha importado la exógena del periodo fiscal {periodo_fiscal_id}"
        )
    return reporte


def listar_topes_exogena(
    session: Session, contador_id: int, contribuyente_id: int, reporte_exogena_id: int
) -> List[TopeExogena]:
    obtener_reporte_exogena(session, contador_id, contribuyente_id, reporte_exogena_id)
    return list(
        session.exec(
            select(TopeExogena)
            .where(TopeExogena.reporte_exogena_id == reporte_exogena_id)
            .order_by(TopeExogena.id)
        ).all()
    )


def listar_registros_exogena(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    reporte_exogena_id: int,
    concepto_code: Optional[str] = None,
    nit_reportante: Optional[str] = None,
) -> List[RegistroExogena]:
    obtener_reporte_exogena(session, contador_id, contribuyente_id, reporte_exogena_id)

    consulta = select(RegistroExogena).where(
        RegistroExogena.reporte_exogena_id == reporte_exogena_id
    )
    if concepto_code:
        consulta = consulta.where(RegistroExogena.concepto_code == concepto_code)
    if nit_reportante:
        consulta = consulta.where(RegistroExogena.nit_reportante == nit_reportante)
    consulta = consulta.order_by(
        RegistroExogena.concepto_code,
        RegistroExogena.nit_reportante,
        RegistroExogena.id,
    )

    return list(session.exec(consulta).all())
