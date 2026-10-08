"""Excepciones tipadas que la capa de servicios usa para señalar errores de
negocio. Los routers las capturan y las traducen a códigos HTTP — los
servicios nunca conocen HTTP ni FastAPI (ver documentacion/04-arquitectura.md,
capa de lógica de negocio).
"""


class ErrorAplicacion(Exception):
    """Excepción base de la capa de servicios."""


class ContadorYaExisteError(ErrorAplicacion):
    """Ya existe un contador registrado con ese email."""


class CredencialesInvalidasError(ErrorAplicacion):
    """El email o la contraseña no corresponden a un contador registrado."""


class ContribuyenteNoEncontradoError(ErrorAplicacion):
    """El contribuyente no existe, o no pertenece al contador autenticado."""


class ContribuyenteConDatosError(ErrorAplicacion):
    """No se puede eliminar un contribuyente que ya tiene periodos fiscales o
    inventario registrado, ni pasar a ASALARIADO uno que maneja inventario."""


class ActivoNoEncontradoError(ErrorAplicacion):
    """El activo no existe, o no pertenece a ese contribuyente."""


class FuenteIngresoNoEncontradaError(ErrorAplicacion):
    """La fuente de ingreso no existe, o no pertenece a ese contribuyente."""


class ActivoDeCierreError(ErrorAplicacion):
    """El Activo INVENTARIO lo crea y lo borra el cierre de periodo: no se
    edita ni se elimina a mano (HU-15)."""


class PeriodoFiscalNoEncontradoError(ErrorAplicacion):
    """El periodo fiscal no existe, o no pertenece a ese contribuyente."""


class PeriodoFiscalDuplicadoError(ErrorAplicacion):
    """El contribuyente ya tiene un periodo fiscal para ese año gravable."""


class PeriodoFiscalCerradoError(ErrorAplicacion):
    """El periodo fiscal está CERRADO: no admite movimientos ni nuevas
    importaciones de exógena (HU-15)."""


class EstadoPeriodoInvalidoError(ErrorAplicacion):
    """El periodo no está en el estado que exige la operación: cerrar uno ya
    cerrado, reabrir uno abierto, cerrar con años anteriores abiertos o
    reabrir con años posteriores cerrados (HU-15)."""


class ArchivoExogenaInvalidoError(ErrorAplicacion):
    """El archivo no tiene el formato esperado (no se encontró la fila de
    encabezados "NIT" / "Nombre...") — no es un error de fila individual,
    es que el archivo completo no parece ser el de la DIAN."""


class ReporteExogenaNoEncontradoError(ErrorAplicacion):
    """El reporte de exógena no existe, o no pertenece a ese contribuyente."""


class UmbralNoConfiguradoError(ErrorAplicacion):
    """No hay UmbralDeclaracion registrado para el año gravable pedido —
    no se puede calcular la obligación de declarar sin ese dato."""


class InventarioNoAplicaError(ErrorAplicacion):
    """El contribuyente es ASALARIADO: el inventario solo aplica a
    contribuyentes INDEPENDIENTE o MIXTO (HU-01, HU-11)."""


class CategoriaNoEncontradaError(ErrorAplicacion):
    """La categoría no existe, o no pertenece a ese contribuyente."""


class CategoriaConProductosActivosError(ErrorAplicacion):
    """No se puede eliminar una categoría con productos activos (HU-11)."""


class ProductoNoEncontradoError(ErrorAplicacion):
    """El producto no existe, o no pertenece a ese contribuyente."""


class ProductoDuplicadoError(ErrorAplicacion):
    """El contribuyente ya tiene un producto con ese código."""


class ProductoInactivoError(ErrorAplicacion):
    """El producto está desactivado: no admite nuevos movimientos."""


class CambioMetodoCosteoError(ErrorAplicacion):
    """No se puede cambiar el método de costeo de un producto que ya tiene
    movimientos: alteraría retroactivamente su costo de ventas (HU-14)."""


class ProveedorNoEncontradoError(ErrorAplicacion):
    """El proveedor no existe, o no pertenece a ese contribuyente."""


class ProveedorDuplicadoError(ErrorAplicacion):
    """Ya existe un proveedor con esa identificación para el contribuyente
    (HU-13)."""


class DocumentoSoporteNoEncontradoError(ErrorAplicacion):
    """El documento soporte no existe, o no pertenece a ese contribuyente."""


class DocumentoSoporteDuplicadoError(ErrorAplicacion):
    """Ya existe un documento soporte del mismo tipo y número."""


class StockInsuficienteError(ErrorAplicacion):
    """La salida dejaría el stock del producto en negativo (HU-12)."""


class MovimientoInvalidoError(ErrorAplicacion):
    """El movimiento no es coherente con su contexto (fecha fuera del año
    del periodo, proveedor en una salida, etc.)."""
