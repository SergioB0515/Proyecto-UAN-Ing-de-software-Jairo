import csv
import hashlib
import io
import os
import re
import tempfile
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional, Tuple

from sqlalchemy import and_, extract, func, or_
from sqlmodel import Session, select

from core.config import ALMACEN_ADJUNTOS, TAMANO_MAXIMO_ADJUNTO_MB
from core.excepciones import (
    ActivoDeCierreError,
    AdjuntoDuplicadoError,
    AdjuntoNoEncontradoError,
    ArchivoDemasiadoGrandeError,
    ArchivoNoPermitidoError,
    EntidadAdjuntoNoEncontradaError,
    PeriodoFiscalCerradoError,
)

from ..contribuyentes.modelos import (
    Activo,
    EstadoPeriodo,
    FuenteIngreso,
    PeriodoFiscal,
    TipoActivo,
)
from ..contribuyentes.servicios import (
    obtener_contribuyente,
    obtener_periodo_fiscal,
)
from ..inventario.modelos import Producto
from ..movimientos.modelos import DocumentoSoporte, Movimiento, Proveedor, TipoMovimiento
from .modelos import (
    Adjunto,
    AdjuntoActualizar,
    AdjuntoLeer,
    CategoriaAdjunto,
    ConteoAdjuntos,
    TipoEntidadAdjunto,
)

PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"
GIF = "image/gif"
WEBP = "image/webp"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CSV = "text/csv"
TXT = "text/plain"

EXTENSIONES_POR_TIPO = {
    PDF: (".pdf",),
    PNG: (".png",),
    JPEG: (".jpg", ".jpeg"),
    GIF: (".gif",),
    WEBP: (".webp",),
    XLSX: (".xlsx",),
    DOCX: (".docx",),
    CSV: (".csv",),
    TXT: (".txt",),
}

TIPOS_PREVISUALIZABLES = frozenset({PDF, PNG, JPEG, GIF, WEBP})

DESCRIPCION_FORMATOS = "PDF, imágenes (PNG, JPG, WEBP, GIF), Excel, Word, CSV o TXT"

CARPETAS_ZIP = {
    TipoEntidadAdjunto.CONTRIBUYENTE: "General",
    TipoEntidadAdjunto.PERIODO_FISCAL: "Declaración del año",
    TipoEntidadAdjunto.ACTIVO: "Activos",
    TipoEntidadAdjunto.FUENTE_INGRESO: "Ingresos",
    TipoEntidadAdjunto.DOCUMENTO_SOPORTE: "Documentos soporte",
    TipoEntidadAdjunto.MOVIMIENTO: "Movimientos",
    TipoEntidadAdjunto.PROVEEDOR: "Proveedores",
}


@dataclass
class EntidadResuelta:
    periodo_fiscal_id: Optional[int]
    etiqueta: str


def _tipo_ooxml(contenido: bytes) -> Optional[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
            nombres = set(archivo.namelist())
    except zipfile.BadZipFile:
        return None
    if "[Content_Types].xml" in nombres:
        if "xl/workbook.xml" in nombres:
            return XLSX
        if "word/document.xml" in nombres:
            return DOCX
    return None


def detectar_tipo(contenido: bytes, nombre: str) -> str:
    if contenido[:1024].find(b"%PDF-") != -1:
        return PDF
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if contenido.startswith(b"\xff\xd8\xff"):
        return JPEG
    if contenido[:6] in (b"GIF87a", b"GIF89a"):
        return GIF
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return WEBP
    if contenido.startswith(b"PK\x03\x04"):
        tipo = _tipo_ooxml(contenido)
        if tipo is not None:
            return tipo
    else:
        extension = os.path.splitext(nombre)[1].lower()
        if extension in (".csv", ".txt") and b"\x00" not in contenido:
            return CSV if extension == ".csv" else TXT
    raise ArchivoNoPermitidoError(
        f"Formato no admitido. Sube {DESCRIPCION_FORMATOS}."
    )


def _limpiar_nombre(nombre: Optional[str]) -> str:
    base = (nombre or "").replace("\\", "/").split("/")[-1]
    base = unicodedata.normalize("NFC", base)
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().strip(".")
    return base or "archivo"


def _nombre_con_extension(nombre: str, tipo: str) -> str:
    raiz, extension = os.path.splitext(nombre)
    if extension.lower() in EXTENSIONES_POR_TIPO[tipo]:
        resultado = nombre
    else:
        resultado = (raiz or "archivo") + EXTENSIONES_POR_TIPO[tipo][0]
    if len(resultado) > 255:
        raiz, extension = os.path.splitext(resultado)
        resultado = raiz[: 255 - len(extension)] + extension
    return resultado


def _directorio_almacen() -> Path:
    return Path(ALMACEN_ADJUNTOS).resolve()


def _ruta_absoluta(ruta_relativa: str) -> Path:
    base = _directorio_almacen()
    ruta = (base / ruta_relativa).resolve()
    if base != ruta and base not in ruta.parents:
        raise AdjuntoNoEncontradoError("La ruta del archivo no es válida")
    return ruta


def _resolver_entidad(
    session: Session, contribuyente_id: int, tipo: TipoEntidadAdjunto, entidad_id: int
) -> EntidadResuelta:
    def no_existe(nombre: str) -> EntidadAdjuntoNoEncontradaError:
        return EntidadAdjuntoNoEncontradaError(
            f"No existe {nombre} {entidad_id} para el contribuyente {contribuyente_id}"
        )

    if tipo == TipoEntidadAdjunto.CONTRIBUYENTE:
        if entidad_id != contribuyente_id:
            raise no_existe("el contribuyente")
        return EntidadResuelta(None, "Documentos generales")

    if tipo == TipoEntidadAdjunto.PERIODO_FISCAL:
        periodo = session.get(PeriodoFiscal, entidad_id)
        if periodo is None or periodo.contribuyente_id != contribuyente_id:
            raise no_existe("el año gravable")
        return EntidadResuelta(periodo.id, f"Año gravable {periodo.anio_gravable}")

    if tipo == TipoEntidadAdjunto.ACTIVO:
        activo = session.get(Activo, entidad_id)
        if activo is None or activo.contribuyente_id != contribuyente_id:
            raise no_existe("el activo")
        if activo.tipo == TipoActivo.INVENTARIO:
            raise ActivoDeCierreError(
                "El inventario lo genera el cierre del periodo y no admite adjuntos: "
                "adjunta los soportes a los movimientos o a sus documentos"
            )
        return EntidadResuelta(activo.periodo_fiscal_id, activo.descripcion)

    if tipo == TipoEntidadAdjunto.FUENTE_INGRESO:
        fuente = session.get(FuenteIngreso, entidad_id)
        if fuente is None or fuente.contribuyente_id != contribuyente_id:
            raise no_existe("la fuente de ingreso")
        return EntidadResuelta(fuente.periodo_fiscal_id, fuente.concepto)

    if tipo == TipoEntidadAdjunto.DOCUMENTO_SOPORTE:
        documento = session.get(DocumentoSoporte, entidad_id)
        if documento is None or documento.contribuyente_id != contribuyente_id:
            raise no_existe("el documento soporte")
        return EntidadResuelta(None, _etiqueta_documento(documento))

    if tipo == TipoEntidadAdjunto.MOVIMIENTO:
        movimiento = session.get(Movimiento, entidad_id)
        if movimiento is None or movimiento.contribuyente_id != contribuyente_id:
            raise no_existe("el movimiento")
        producto = session.get(Producto, movimiento.producto_id)
        return EntidadResuelta(movimiento.periodo_fiscal_id, _etiqueta_movimiento(movimiento, producto))

    proveedor = session.get(Proveedor, entidad_id)
    if proveedor is None or proveedor.contribuyente_id != contribuyente_id:
        raise no_existe("el proveedor")
    return EntidadResuelta(None, proveedor.nombre)


def _etiqueta_documento(documento: DocumentoSoporte) -> str:
    return f"{documento.tipo.value.replace('_', ' ').capitalize()} {documento.numero}"


def _etiqueta_movimiento(movimiento: Movimiento, producto: Optional[Producto]) -> str:
    accion = "Compra" if movimiento.tipo == TipoMovimiento.ENTRADA else "Venta"
    nombre = producto.nombre if producto is not None else f"producto {movimiento.producto_id}"
    return f"{accion} de {nombre} ({movimiento.fecha.isoformat()})"


def _etiquetas(
    session: Session, contribuyente_id: int, adjuntos: List[Adjunto]
) -> Dict[Tuple[TipoEntidadAdjunto, int], str]:
    ids: Dict[TipoEntidadAdjunto, set] = {}
    for adjunto in adjuntos:
        ids.setdefault(adjunto.entidad_tipo, set()).add(adjunto.entidad_id)

    etiquetas: Dict[Tuple[TipoEntidadAdjunto, int], str] = {}

    def anotar(tipo: TipoEntidadAdjunto, modelo, formato) -> None:
        if tipo not in ids:
            return
        filas = session.exec(
            select(modelo).where(
                modelo.id.in_(ids[tipo]), modelo.contribuyente_id == contribuyente_id
            )
        ).all()
        for fila in filas:
            etiquetas[(tipo, fila.id)] = formato(fila)

    if TipoEntidadAdjunto.CONTRIBUYENTE in ids:
        etiquetas[(TipoEntidadAdjunto.CONTRIBUYENTE, contribuyente_id)] = "Documentos generales"
    anotar(TipoEntidadAdjunto.PERIODO_FISCAL, PeriodoFiscal, lambda p: f"Año gravable {p.anio_gravable}")
    anotar(TipoEntidadAdjunto.ACTIVO, Activo, lambda a: a.descripcion)
    anotar(TipoEntidadAdjunto.FUENTE_INGRESO, FuenteIngreso, lambda f: f.concepto)
    anotar(TipoEntidadAdjunto.DOCUMENTO_SOPORTE, DocumentoSoporte, _etiqueta_documento)
    anotar(TipoEntidadAdjunto.PROVEEDOR, Proveedor, lambda p: p.nombre)

    if TipoEntidadAdjunto.MOVIMIENTO in ids:
        movimientos = session.exec(
            select(Movimiento).where(
                Movimiento.id.in_(ids[TipoEntidadAdjunto.MOVIMIENTO]),
                Movimiento.contribuyente_id == contribuyente_id,
            )
        ).all()
        productos = {
            p.id: p
            for p in session.exec(
                select(Producto).where(Producto.id.in_({m.producto_id for m in movimientos}))
            ).all()
        }
        for movimiento in movimientos:
            etiquetas[(TipoEntidadAdjunto.MOVIMIENTO, movimiento.id)] = _etiqueta_movimiento(
                movimiento, productos.get(movimiento.producto_id)
            )
    return etiquetas


def _a_lectura(adjunto: Adjunto, etiquetas: Dict[Tuple[TipoEntidadAdjunto, int], str]) -> AdjuntoLeer:
    return AdjuntoLeer(
        id=adjunto.id,
        contribuyente_id=adjunto.contribuyente_id,
        entidad_tipo=adjunto.entidad_tipo,
        entidad_id=adjunto.entidad_id,
        etiqueta_entidad=etiquetas.get((adjunto.entidad_tipo, adjunto.entidad_id)),
        periodo_fiscal_id=adjunto.periodo_fiscal_id,
        categoria=adjunto.categoria,
        descripcion=adjunto.descripcion,
        nombre_original=adjunto.nombre_original,
        tipo_mime=adjunto.tipo_mime,
        tamano_bytes=adjunto.tamano_bytes,
        creado_en=adjunto.creado_en,
        previsualizable=adjunto.tipo_mime in TIPOS_PREVISUALIZABLES,
    )


def a_lecturas(session: Session, contribuyente_id: int, adjuntos: List[Adjunto]) -> List[AdjuntoLeer]:
    etiquetas = _etiquetas(session, contribuyente_id, adjuntos)
    return [_a_lectura(a, etiquetas) for a in adjuntos]


def _limpiar_descripcion(descripcion: Optional[str]) -> Optional[str]:
    if descripcion is None:
        return None
    return descripcion.strip() or None


def adjuntar_archivo(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    entidad_tipo: TipoEntidadAdjunto,
    entidad_id: int,
    flujo: BinaryIO,
    nombre: Optional[str],
    categoria: CategoriaAdjunto = CategoriaAdjunto.OTRO,
    descripcion: Optional[str] = None,
) -> AdjuntoLeer:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    entidad = _resolver_entidad(session, contribuyente_id, entidad_tipo, entidad_id)

    limite = int(TAMANO_MAXIMO_ADJUNTO_MB * 1024 * 1024)
    contenido = flujo.read(limite + 1)
    if len(contenido) > limite:
        raise ArchivoDemasiadoGrandeError(
            f"El archivo supera el máximo de {TAMANO_MAXIMO_ADJUNTO_MB:g} MB"
        )
    if not contenido:
        raise ArchivoNoPermitidoError("El archivo está vacío")

    nombre_limpio = _limpiar_nombre(nombre)
    tipo = detectar_tipo(contenido, nombre_limpio)
    huella = hashlib.sha256(contenido).hexdigest()

    repetido = session.exec(
        select(Adjunto.id).where(
            Adjunto.contribuyente_id == contribuyente_id,
            Adjunto.entidad_tipo == entidad_tipo,
            Adjunto.entidad_id == entidad_id,
            Adjunto.sha256 == huella,
        )
    ).first()
    if repetido is not None:
        raise AdjuntoDuplicadoError(f"«{nombre_limpio}» ya está adjunto a este objeto")

    nombre_final = _nombre_con_extension(nombre_limpio, tipo)
    ruta_relativa = f"{contribuyente_id}/{uuid.uuid4().hex}{EXTENSIONES_POR_TIPO[tipo][0]}"
    ruta = _ruta_absoluta(ruta_relativa)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "xb") as destino:
        destino.write(contenido)

    adjunto = Adjunto(
        contribuyente_id=contribuyente_id,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        periodo_fiscal_id=entidad.periodo_fiscal_id,
        categoria=categoria,
        descripcion=_limpiar_descripcion(descripcion),
        nombre_original=nombre_final,
        ruta_relativa=ruta_relativa,
        tipo_mime=tipo,
        tamano_bytes=len(contenido),
        sha256=huella,
    )
    try:
        session.add(adjunto)
        session.commit()
    except Exception:
        session.rollback()
        borrar_archivos([ruta_relativa])
        raise
    session.refresh(adjunto)
    return _a_lectura(adjunto, {(entidad_tipo, entidad_id): entidad.etiqueta})


def _condicion_periodo(contribuyente_id: int, periodo: PeriodoFiscal):
    documentos_del_anio = select(DocumentoSoporte.id).where(
        DocumentoSoporte.contribuyente_id == contribuyente_id,
        extract("year", DocumentoSoporte.fecha) == periodo.anio_gravable,
    )
    return or_(
        Adjunto.periodo_fiscal_id == periodo.id,
        and_(
            Adjunto.entidad_tipo == TipoEntidadAdjunto.DOCUMENTO_SOPORTE,
            Adjunto.entidad_id.in_(documentos_del_anio),
        ),
    )


def _consulta_adjuntos(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    entidad_tipo: Optional[TipoEntidadAdjunto],
    entidad_id: Optional[int],
    periodo_fiscal_id: Optional[int],
    categoria: Optional[CategoriaAdjunto],
    texto: Optional[str],
    incluir_generales: bool = False,
):
    obtener_contribuyente(session, contador_id, contribuyente_id)
    consulta = select(Adjunto).where(Adjunto.contribuyente_id == contribuyente_id)
    if entidad_tipo is not None:
        consulta = consulta.where(Adjunto.entidad_tipo == entidad_tipo)
    if entidad_id is not None:
        consulta = consulta.where(Adjunto.entidad_id == entidad_id)
    if periodo_fiscal_id is not None:
        periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
        condicion = _condicion_periodo(contribuyente_id, periodo)
        if incluir_generales:
            condicion = or_(condicion, Adjunto.entidad_tipo == TipoEntidadAdjunto.CONTRIBUYENTE)
        consulta = consulta.where(condicion)
    if categoria is not None:
        consulta = consulta.where(Adjunto.categoria == categoria)
    texto = (texto or "").strip()
    if texto:
        escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        patron = f"%{escapado}%"
        consulta = consulta.where(
            or_(
                Adjunto.nombre_original.ilike(patron, escape="\\"),
                Adjunto.descripcion.ilike(patron, escape="\\"),
            )
        )
    return consulta.order_by(Adjunto.creado_en.desc(), Adjunto.id.desc())


def listar_adjuntos(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    entidad_tipo: Optional[TipoEntidadAdjunto] = None,
    entidad_id: Optional[int] = None,
    periodo_fiscal_id: Optional[int] = None,
    categoria: Optional[CategoriaAdjunto] = None,
    texto: Optional[str] = None,
    incluir_generales: bool = False,
) -> List[AdjuntoLeer]:
    consulta = _consulta_adjuntos(
        session,
        contador_id,
        contribuyente_id,
        entidad_tipo,
        entidad_id,
        periodo_fiscal_id,
        categoria,
        texto,
        incluir_generales,
    )
    adjuntos = list(session.exec(consulta).all())
    return a_lecturas(session, contribuyente_id, adjuntos)


def contar_adjuntos(session: Session, contador_id: int, contribuyente_id: int) -> List[ConteoAdjuntos]:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    filas = session.exec(
        select(Adjunto.entidad_tipo, Adjunto.entidad_id, func.count(Adjunto.id))
        .where(Adjunto.contribuyente_id == contribuyente_id)
        .group_by(Adjunto.entidad_tipo, Adjunto.entidad_id)
    ).all()
    return [ConteoAdjuntos(entidad_tipo=t, entidad_id=i, total=n) for t, i, n in filas]


def _obtener(session: Session, contribuyente_id: int, adjunto_id: int) -> Adjunto:
    adjunto = session.get(Adjunto, adjunto_id)
    if adjunto is None or adjunto.contribuyente_id != contribuyente_id:
        raise AdjuntoNoEncontradoError(
            f"No existe el adjunto {adjunto_id} para el contribuyente {contribuyente_id}"
        )
    return adjunto


def obtener_archivo(
    session: Session, contador_id: int, contribuyente_id: int, adjunto_id: int
) -> Tuple[Adjunto, Path]:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    adjunto = _obtener(session, contribuyente_id, adjunto_id)
    ruta = _ruta_absoluta(adjunto.ruta_relativa)
    if not ruta.is_file():
        raise AdjuntoNoEncontradoError(
            f"El archivo de «{adjunto.nombre_original}» ya no está en el almacén"
        )
    return adjunto, ruta


def actualizar_adjunto(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    adjunto_id: int,
    cambios: AdjuntoActualizar,
) -> AdjuntoLeer:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    adjunto = _obtener(session, contribuyente_id, adjunto_id)
    datos = cambios.model_dump(exclude_unset=True)
    if "descripcion" in datos:
        adjunto.descripcion = _limpiar_descripcion(datos["descripcion"])
    if datos.get("categoria") is not None:
        adjunto.categoria = datos["categoria"]
    session.add(adjunto)
    session.commit()
    session.refresh(adjunto)
    return a_lecturas(session, contribuyente_id, [adjunto])[0]


def eliminar_adjunto(
    session: Session, contador_id: int, contribuyente_id: int, adjunto_id: int
) -> None:
    obtener_contribuyente(session, contador_id, contribuyente_id)
    adjunto = _obtener(session, contribuyente_id, adjunto_id)
    if adjunto.periodo_fiscal_id is not None:
        periodo = session.get(PeriodoFiscal, adjunto.periodo_fiscal_id)
        if periodo is not None and periodo.estado == EstadoPeriodo.CERRADO:
            raise PeriodoFiscalCerradoError(
                f"El periodo {periodo.anio_gravable} está cerrado: reábrelo para eliminar soportes"
            )
    ruta_relativa = adjunto.ruta_relativa
    session.delete(adjunto)
    session.commit()
    borrar_archivos([ruta_relativa])


def quitar_de_entidad(
    session: Session, contribuyente_id: int, entidad_tipo: TipoEntidadAdjunto, entidad_id: int
) -> List[str]:
    adjuntos = session.exec(
        select(Adjunto).where(
            Adjunto.contribuyente_id == contribuyente_id,
            Adjunto.entidad_tipo == entidad_tipo,
            Adjunto.entidad_id == entidad_id,
        )
    ).all()
    rutas = [a.ruta_relativa for a in adjuntos]
    for adjunto in adjuntos:
        session.delete(adjunto)
    return rutas


def quitar_todos_del_contribuyente(session: Session, contribuyente_id: int) -> List[str]:
    adjuntos = session.exec(
        select(Adjunto).where(Adjunto.contribuyente_id == contribuyente_id)
    ).all()
    rutas = [a.ruta_relativa for a in adjuntos]
    for adjunto in adjuntos:
        session.delete(adjunto)
    return rutas


def borrar_archivos(rutas_relativas: List[str]) -> None:
    for ruta_relativa in rutas_relativas:
        try:
            _ruta_absoluta(ruta_relativa).unlink(missing_ok=True)
        except (OSError, AdjuntoNoEncontradoError):
            continue


def _nombre_para_zip(texto: str, por_defecto: str = "sin nombre") -> str:
    texto = unicodedata.normalize("NFC", texto)
    texto = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "_", texto).strip(" .")
    return texto[:80] or por_defecto


def _ruta_unica(carpeta: str, nombre: str, usados: set) -> str:
    raiz, extension = os.path.splitext(nombre)
    candidato = f"{carpeta}/{nombre}"
    numero = 2
    while candidato.lower() in usados:
        candidato = f"{carpeta}/{raiz} ({numero}){extension}"
        numero += 1
    usados.add(candidato.lower())
    return candidato


def comprimir_soportes(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> Tuple[BinaryIO, int, str]:
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    periodo = obtener_periodo_fiscal(session, contador_id, contribuyente_id, periodo_fiscal_id)
    adjuntos = list(
        session.exec(
            select(Adjunto)
            .where(
                Adjunto.contribuyente_id == contribuyente_id,
                or_(
                    _condicion_periodo(contribuyente_id, periodo),
                    Adjunto.entidad_tipo == TipoEntidadAdjunto.CONTRIBUYENTE,
                ),
            )
            .order_by(Adjunto.entidad_tipo, Adjunto.entidad_id, Adjunto.id)
        ).all()
    )
    etiquetas = _etiquetas(session, contribuyente_id, adjuntos)

    destino = tempfile.TemporaryFile()
    usados: set = set()
    indice = io.StringIO()
    escritor = csv.writer(indice)
    escritor.writerow(["Archivo en el ZIP", "Objeto", "Categoría", "Descripción", "Nombre original", "Cargado"])
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zip_:
        for adjunto in adjuntos:
            ruta = _ruta_absoluta(adjunto.ruta_relativa)
            if not ruta.is_file():
                continue
            etiqueta = etiquetas.get((adjunto.entidad_tipo, adjunto.entidad_id), "")
            carpeta = CARPETAS_ZIP[adjunto.entidad_tipo]
            if adjunto.entidad_tipo not in (
                TipoEntidadAdjunto.CONTRIBUYENTE,
                TipoEntidadAdjunto.PERIODO_FISCAL,
            ):
                carpeta = f"{carpeta}/{_nombre_para_zip(etiqueta)}"
            nombre = _nombre_para_zip(adjunto.nombre_original, "archivo")
            ruta_zip = _ruta_unica(carpeta, nombre, usados)
            zip_.write(ruta, ruta_zip)
            escritor.writerow(
                [
                    ruta_zip,
                    etiqueta,
                    adjunto.categoria.value,
                    adjunto.descripcion or "",
                    adjunto.nombre_original,
                    adjunto.creado_en.strftime("%Y-%m-%d %H:%M"),
                ]
            )
        zip_.writestr("indice.csv", "\ufeff" + indice.getvalue())
    tamano = destino.tell()
    destino.seek(0)
    nombre_zip = f"soportes_{_nombre_para_zip(contribuyente.rut, 'contribuyente')}_{periodo.anio_gravable}.zip"
    return destino, tamano, nombre_zip
