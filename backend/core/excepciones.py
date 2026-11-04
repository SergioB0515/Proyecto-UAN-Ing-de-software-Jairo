class ErrorAplicacion(Exception):
    pass


class ContadorYaExisteError(ErrorAplicacion):
    pass


class CredencialesInvalidasError(ErrorAplicacion):
    pass


class CuentaBloqueadaError(ErrorAplicacion):
    def __init__(self, mensaje: str, segundos: int):
        super().__init__(mensaje)
        self.segundos = segundos


class ContrasenaActualIncorrectaError(ErrorAplicacion):
    pass


class ArchivoDemasiadoGrandeError(ErrorAplicacion):
    pass


class CalendarioInvalidoError(ErrorAplicacion):
    pass


class CalendarioOficialNoDisponibleError(ErrorAplicacion):
    pass


class ContribuyenteNoEncontradoError(ErrorAplicacion):
    pass


class ContribuyenteConDatosError(ErrorAplicacion):
    pass


class SinPeriodoAnteriorError(ErrorAplicacion):
    pass


class ActivoNoEncontradoError(ErrorAplicacion):
    pass


class FuenteIngresoNoEncontradaError(ErrorAplicacion):
    pass


class ActivoDeCierreError(ErrorAplicacion):
    pass


class PeriodoFiscalNoEncontradoError(ErrorAplicacion):
    pass


class PeriodoFiscalDuplicadoError(ErrorAplicacion):
    pass


class PeriodoFiscalCerradoError(ErrorAplicacion):
    pass


class EstadoPeriodoInvalidoError(ErrorAplicacion):
    pass


class ArchivoExogenaInvalidoError(ErrorAplicacion):
    pass


class ReporteExogenaNoEncontradoError(ErrorAplicacion):
    pass


class UmbralNoConfiguradoError(ErrorAplicacion):
    pass


class InventarioNoAplicaError(ErrorAplicacion):
    pass


class CategoriaNoEncontradaError(ErrorAplicacion):
    pass


class CategoriaConProductosActivosError(ErrorAplicacion):
    pass


class ProductoNoEncontradoError(ErrorAplicacion):
    pass


class ProductoDuplicadoError(ErrorAplicacion):
    pass


class ProductoInactivoError(ErrorAplicacion):
    pass


class CambioMetodoCosteoError(ErrorAplicacion):
    pass


class ProveedorNoEncontradoError(ErrorAplicacion):
    pass


class ProveedorDuplicadoError(ErrorAplicacion):
    pass


class DocumentoSoporteNoEncontradoError(ErrorAplicacion):
    pass


class DocumentoSoporteDuplicadoError(ErrorAplicacion):
    pass


class StockInsuficienteError(ErrorAplicacion):
    pass


class MovimientoInvalidoError(ErrorAplicacion):
    pass


class AdjuntoNoEncontradoError(ErrorAplicacion):
    pass


class AdjuntoDuplicadoError(ErrorAplicacion):
    pass


class ArchivoNoPermitidoError(ErrorAplicacion):
    pass


class EntidadAdjuntoNoEncontradaError(ErrorAplicacion):
    pass


class EntidadSinAdjuntosError(ErrorAplicacion):
    pass


class AnioGravableNoSoportadoError(ErrorAplicacion):
    """El año gravable no tiene parámetros tributarios cargados."""


class DeduccionNoEncontradaError(ErrorAplicacion):
    pass


class PerdidaNoEncontradaError(ErrorAplicacion):
    pass


class PagoEfectivoNoEncontradoError(ErrorAplicacion):
    pass


class PlantillaNoEncontradaError(ErrorAplicacion):
    pass
