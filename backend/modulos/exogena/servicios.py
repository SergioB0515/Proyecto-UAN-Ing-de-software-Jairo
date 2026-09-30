
import io
import re
from typing import List, Optional

import pandas as pd
from sqlmodel import Session, select

from core.excepciones import (
    ArchivoExogenaInvalidoError,
    PeriodoFiscalNoEncontradoError,
)

from ..contribuyentes.modelos import PeriodoFiscal
from ..contribuyentes.servicios import obtener_contribuyente
from .modelos import (
    ConsultanteInfo,
    FilaConError,
    RegistroExogena,
    RegistroExogenaBase,
    ReporteExogena,
    ResultadoParseo,
    TopeExogena,
    TopeExogenaBase,
)

PATRON_CONCEPTO = re.compile(r"\(Concepto:\s*(\d+)\)", re.IGNORECASE)

PATRON_RENGLON = re.compile(r"\bR\d+\b")

NIT_DIAN = "800197268"


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
            if valor != valor:  # NaN
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
        renglones = PATRON_RENGLON.findall(uso or "")

        resultado.registros.append(
            RegistroExogenaBase(
                nit_reportante=nit,
                nombre_reportante=_texto(_col(fila, 1)) or "",
                detalle=detalle,
                concepto_code=match_concepto.group(1) if match_concepto else None,
                renglones_sugeridos=", ".join(renglones) if renglones else None,
                valor=valor,
                uso_sugerido=uso,
                info_adicional=_texto(_col(fila, 7)),
                es_auto_reportado=nit == consultante.identificacion,
                es_dian=nit == NIT_DIAN,
            )
        )

    return resultado


def _celda(valor):
    """Normaliza una celda cruda de pandas: NaN/vacío -> None."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    if isinstance(valor, str) and not valor.strip():
        return None
    return valor


def _col(fila, indice):
    return fila[indice] if indice < len(fila) else None


def _texto(valor) -> Optional[str]:
    """Convierte una celda a texto limpio; enteros que vienen como float
    (ej. NIT 900123.0) se muestran sin decimales."""
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
) -> ReporteExogena:
    obtener_contribuyente(session, contador_id, contribuyente_id)

    periodo = session.exec(
        select(PeriodoFiscal).where(
            PeriodoFiscal.id == periodo_fiscal_id,
            PeriodoFiscal.contribuyente_id == contribuyente_id,
        )
    ).first()
    if periodo is None:
        raise PeriodoFiscalNoEncontradoError(
            "El periodo fiscal no existe o no pertenece a este contribuyente"
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
    return reporte


def listar_registros_exogena(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    reporte_exogena_id: int,
    concepto_code: Optional[str] = None,
    nit_reportante: Optional[str] = None,
) -> List[RegistroExogena]:
    obtener_contribuyente(session, contador_id, contribuyente_id)

    consulta = select(RegistroExogena).where(
        RegistroExogena.reporte_exogena_id == reporte_exogena_id
    )
    if concepto_code:
        consulta = consulta.where(RegistroExogena.concepto_code == concepto_code)
    if nit_reportante:
        consulta = consulta.where(RegistroExogena.nit_reportante == nit_reportante)

    return list(session.exec(consulta).all())
