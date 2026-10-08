"""Auditoría centralizada: en vez de llamar a «registrar evento» en cada
endpoint, este middleware revisa cada petición terminada y, si fue una
acción auditable que tuvo éxito, la registra con el contador del token, el
contribuyente de la ruta y la IP.

Si el contribuyente no está en la ruta (al crearlo), el endpoint lo deja
en `request.state.auditoria_contribuyente_id`.

Qué es auditable lo decide ACCIONES_AUDITADAS (nombre del endpoint ->
descripción legible). Un endpoint nuevo que modifique datos debe agregarse
aquí; la prueba `test_todo_endpoint_que_modifica_esta_auditado` falla si
se olvida.
"""
from typing import Optional

from sqlmodel import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.seguridad import decodificar_token

from .modelos import EventoAuditoria
from .servicios import registrar_evento

ACCIONES_AUDITADAS = {
    # contadores
    "cambiar_contrasena": "Cambió su contraseña",
    # contribuyentes
    "crear": "Registró un contribuyente",
    "actualizar": "Editó los datos del contribuyente",
    "eliminar": "Eliminó un contribuyente",
    "crear_periodo_fiscal": "Abrió un año gravable",
    "copiar_activos": "Copió los activos del año anterior",
    "crear_activo": "Registró un activo",
    "actualizar_activo": "Editó un activo",
    "eliminar_activo": "Eliminó un activo",
    "crear_fuente_ingreso": "Registró una fuente de ingreso",
    "actualizar_fuente_ingreso": "Editó una fuente de ingreso",
    "eliminar_fuente_ingreso": "Eliminó una fuente de ingreso",
    # exógena y parámetros
    "importar_exogena": "Importó un archivo de exógena",
    "registrar_umbral": "Registró o cambió un umbral de declaración",
    # inventario
    "crear_categoria": "Creó una categoría",
    "eliminar_categoria": "Eliminó una categoría",
    "crear_producto": "Creó un producto",
    "actualizar_producto": "Editó un producto",
    "crear_proveedor": "Registró un proveedor",
    "crear_documento_soporte": "Registró un documento soporte",
    "registrar_movimiento": "Registró un movimiento de inventario",
    # cierre y reportes (la descarga también se audita: es salida de datos)
    "cerrar_periodo": "Cerró un año gravable",
    "reabrir_periodo": "Reabrió un año gravable",
    "descargar_reporte": "Descargó un reporte",
}


def ip_cliente(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _contador_id(session, request: Request) -> Optional[int]:
    from ..contadores.modelos import Contador

    encabezado = request.headers.get("authorization", "")
    if not encabezado.lower().startswith("bearer "):
        return None
    email = decodificar_token(encabezado[7:])
    if email is None:
        return None
    return session.exec(select(Contador.id).where(Contador.email == email)).first()


class AuditoriaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        respuesta = await call_next(request)

        ruta = request.scope.get("route")
        nombre = getattr(ruta, "name", None)
        if nombre not in ACCIONES_AUDITADAS or respuesta.status_code >= 400:
            return respuesta

        # La sesión se obtiene igual que en los endpoints (respetando
        # dependency_overrides), para que las pruebas usen su transacción.
        from database import obtener_sesion

        fabrica = request.app.dependency_overrides.get(obtener_sesion, obtener_sesion)
        generador = fabrica()
        session = next(generador)
        try:
            contador_id = _contador_id(session, request)
            if contador_id is None:
                return respuesta
            parametros = request.scope.get("path_params", {})
            contribuyente_id = parametros.get("contribuyente_id") or getattr(
                request.state, "auditoria_contribuyente_id", None
            )
            descripcion = ACCIONES_AUDITADAS[nombre]
            if nombre == "descargar_reporte":
                descripcion += f" ({parametros.get('tipo')}, {request.query_params.get('formato', 'xlsx')})"
            registrar_evento(
                session,
                EventoAuditoria(
                    contador_id=contador_id,
                    contribuyente_id=int(contribuyente_id) if contribuyente_id else None,
                    accion=nombre,
                    descripcion=descripcion,
                    metodo=request.method,
                    ruta=request.url.path,
                    ip=ip_cliente(request),
                ),
            )
        finally:
            generador.close()
        return respuesta
