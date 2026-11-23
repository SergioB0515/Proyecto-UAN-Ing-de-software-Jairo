from typing import Optional

from sqlmodel import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.red import ip_cliente
from core.seguridad import decodificar_token

from .modelos import EventoAuditoria
from .servicios import registrar_evento

ACCIONES_AUDITADAS = {
    "cambiar_contrasena": "Cambió su contraseña",
    "crear_venta_inmueble": "Registró la venta de un inmueble",
    "eliminar_venta_inmueble": "Eliminó la venta de un inmueble",
    "actualizar_seguimiento_declaracion": "Actualizó las etapas de la declaración",
    "registrar_presentacion_declaracion": "Registró la presentación de la declaración",
    "registrar_declaracion_anterior": "Registró una declaración anterior",
    "traer_datos_del_anio_anterior": "Trajo los datos de la declaración anterior",
    "actualizar_documento_solicitado": "Actualizó un documento solicitado al cliente",
    "agregar_documento_solicitado": "Agregó un documento a la solicitud del cliente",
    "guardar_tasa_interes": "Guardó una tasa de interés moratorio",
    "crear": "Registró un contribuyente",
    "actualizar": "Editó los datos del contribuyente",
    "eliminar": "Eliminó un contribuyente",
    "crear_periodo_fiscal": "Abrió un año gravable",
    "actualizar_periodo_fiscal": "Actualizó el seguimiento de la declaración",
    "copiar_activos": "Copió los activos del año anterior",
    "crear_activo": "Registró un activo",
    "actualizar_activo": "Editó un activo",
    "eliminar_activo": "Eliminó un activo",
    "crear_fuente_ingreso": "Registró una fuente de ingreso",
    "actualizar_fuente_ingreso": "Editó una fuente de ingreso",
    "eliminar_fuente_ingreso": "Eliminó una fuente de ingreso",
    "importar_exogena": "Importó un archivo de exógena",
    "registrar_umbral": "Registró o cambió un umbral de declaración",
    "cargar_umbral_oficial": "Cargó los topes oficiales para declarar",
    "reemplazar_plazos": "Cambió el calendario de vencimientos",
    "cargar_calendario_oficial": "Cargó el calendario oficial de vencimientos",
    "crear_categoria": "Creó una categoría",
    "eliminar_categoria": "Eliminó una categoría",
    "crear_producto": "Creó un producto",
    "actualizar_producto": "Editó un producto",
    "crear_proveedor": "Registró un proveedor",
    "crear_documento_soporte": "Registró un documento soporte",
    "registrar_movimiento": "Registró un movimiento de inventario",
    "cerrar_periodo": "Cerró un año gravable",
    "reabrir_periodo": "Reabrió un año gravable",
    "descargar_reporte": "Descargó un reporte",
    "exportar_cartera": "Exportó el panel de cartera",
    "subir_adjunto": "Adjuntó un soporte",
    "actualizar_adjunto": "Editó los datos de un soporte",
    "eliminar_adjunto": "Eliminó un soporte",
    "descargar_soportes": "Descargó los soportes de un año en ZIP",
    # Liquidación: también las decisiones del contador (cédula, deducciones).
    "actualizar_hoja": "Actualizó la hoja de liquidación",
    "crear_deduccion": "Solicitó una deducción o renta exenta",
    "eliminar_deduccion": "Eliminó una deducción solicitada",
    "imputar_deduccion": "Cambió la casilla del formulario de una deducción",
    "clasificar_ingresos": "Clasificó fuentes de ingreso por cédula",
    "exportar_liquidacion": "Exportó el borrador de liquidación",
    "guardar_depreciacion": "Registró datos de depreciación de activos",
    "eliminar_depreciacion": "Quitó la depreciación de un activo",
    "crear_perdida": "Registró una pérdida fiscal de un año anterior",
    "eliminar_perdida": "Eliminó una pérdida fiscal",
    "crear_pago_efectivo": "Registró un pago individual en efectivo",
    "eliminar_pago_efectivo": "Eliminó un pago en efectivo",
    "crear_deduccion_desde_plantilla": "Solicitó una deducción desde el catálogo",
    "copiar_hoja_del_anterior": "Copió la hoja de liquidación del año anterior",
    # Portal de carga: acciones del contador.
    "generar_enlace_carga": "Generó un enlace de carga para el contribuyente",
    "revocar_enlace_carga": "Revocó un enlace de carga",
    "crear_dato_adicional": "Registró un dato que la exógena no reporta",
    "eliminar_dato_adicional": "Eliminó un dato adicional",
    "fijar_decision_renglon": "Fijó el valor final de un renglón",
    "borrar_decision_renglon": "Deshizo el valor final de un renglón",
}

# Acciones que hace el contribuyente desde el enlace de carga, sin cuenta.
#
# Se auditan igual que las del contador, con dos diferencias que el middleware
# resuelve abajo:
#
# 1. El contador no sale de un encabezado `Authorization` —no hay— sino del
#    enlace: se audita bajo el contador dueño del enlace, que es quien
#    responde por esos datos y a quien le sirve el registro.
# 2. La ruta se guarda CENSURADA. El token va en la URL, y escribirlo en la
#    bitácora sería dejar la llave anotada en un registro que después se
#    exporta, se respalda y se consulta desde la aplicación.
ACCIONES_PORTAL = {
    "aceptar_politica": "El contribuyente aceptó la política de tratamiento de datos",
    "cargar_exogena": "El contribuyente cargó el archivo de exógena",
    "responder_documento": "El contribuyente respondió un documento pedido",
    "subir_soporte": "El contribuyente cargó un soporte",
    "agregar_adicional": "El contribuyente registró un dato que la exógena no trae",
    "eliminar_adicional": "El contribuyente eliminó un dato adicional",
}

ACCIONES_AUDITADAS.update(ACCIONES_PORTAL)


def _contador_id(session, request: Request) -> Optional[int]:
    from ..contadores.modelos import Contador

    encabezado = request.headers.get("authorization", "")
    if not encabezado.lower().startswith("bearer "):
        return None
    email = decodificar_token(encabezado[7:])
    if email is None:
        return None
    return session.exec(select(Contador.id).where(Contador.email == email)).first()


def _desde_enlace(session, request: Request):
    """Contador, contribuyente y ruta censurada de una petición del portal.

    Devuelve (None, None, ruta) si el enlace no se puede resolver; el
    middleware entonces no registra nada, igual que cuando no hay sesión.
    """
    from modulos.portal.modelos import EnlaceCarga
    from modulos.portal.servicios import hashear_token

    token = request.scope.get("path_params", {}).get("token")
    if not token:
        return None, None, request.url.path

    ruta = request.url.path.replace(token, f"{token[:4]}…")
    enlace = session.exec(
        select(EnlaceCarga).where(EnlaceCarga.token_hash == hashear_token(token))
    ).first()
    if enlace is None:
        return None, None, ruta
    return enlace.contador_id, enlace.contribuyente_id, ruta


class AuditoriaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        respuesta = await call_next(request)

        ruta = request.scope.get("route")
        nombre = getattr(ruta, "name", None)
        if nombre not in ACCIONES_AUDITADAS or respuesta.status_code >= 400:
            return respuesta

        from database import obtener_sesion

        fabrica = request.app.dependency_overrides.get(obtener_sesion, obtener_sesion)
        generador = fabrica()
        session = next(generador)
        try:
            parametros = request.scope.get("path_params", {})
            ruta = request.url.path
            if nombre in ACCIONES_PORTAL:
                contador_id, contribuyente_id, ruta = _desde_enlace(session, request)
            else:
                contador_id = _contador_id(session, request)
                contribuyente_id = parametros.get("contribuyente_id") or getattr(
                    request.state, "auditoria_contribuyente_id", None
                )
            if contador_id is None:
                return respuesta
            descripcion = ACCIONES_AUDITADAS[nombre]
            formato = request.query_params.get("formato", "xlsx")
            if nombre == "descargar_reporte":
                descripcion += f" ({parametros.get('tipo')}, {formato})"
            elif nombre == "exportar_cartera":
                descripcion += f" ({formato})"
            registrar_evento(
                session,
                EventoAuditoria(
                    contador_id=contador_id,
                    contribuyente_id=int(contribuyente_id) if contribuyente_id else None,
                    accion=nombre,
                    descripcion=descripcion,
                    metodo=request.method,
                    ruta=ruta,
                    ip=ip_cliente(request),
                ),
            )
        finally:
            generador.close()
        return respuesta
