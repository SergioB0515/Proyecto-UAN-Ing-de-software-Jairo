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


class PeriodoFiscalNoEncontradoError(ErrorAplicacion):
    """El periodo fiscal no existe, o no pertenece a ese contribuyente."""


class ArchivoExogenaInvalidoError(ErrorAplicacion):
    """El archivo no tiene el formato esperado (no se encontró la fila de
    encabezados "NIT" / "Nombre...") — no es un error de fila individual,
    es que el archivo completo no parece ser el de la DIAN."""


class ReporteExogenaNoEncontradoError(ErrorAplicacion):
    """El reporte de exógena no existe, o no pertenece a ese contribuyente."""


class UmbralNoConfiguradoError(ErrorAplicacion):
    """No hay UmbralDeclaracion registrado para el año gravable pedido —
    no se puede calcular la obligación de declarar sin ese dato."""
