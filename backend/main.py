import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from core.config import ORIGENES_PERMITIDOS
from database import crear_tablas
from modulos.adjuntos.router import router as router_adjuntos
from modulos.auditoria.middleware import AuditoriaMiddleware
from modulos.auditoria.router import router as router_auditoria
from modulos.cartera.router import router as router_cartera
from modulos.conciliacion.router import router as router_conciliacion
from modulos.contadores.router import router as router_contadores
from modulos.contribuyentes.router import router as router_contribuyentes
from modulos.exogena.router import router as router_exogena
from modulos.inventario.router import router as router_inventario
from modulos.movimientos.router import router as router_movimientos
from modulos.parametros.router import router as router_parametros
from modulos.reportes.router import router as router_reportes


def _sembrar_demo_si_corresponde() -> None:
    """Carga los datos de demostración al arrancar, si así se pidió.

    Pensado para un despliegue donde no hay terminal a mano (Render, Railway):
    basta con definir SEMBRAR_DEMO_AL_ARRANCAR=1.

    En los arranques siguientes no vuelve a sembrar, pero sí regenera los
    archivos de los soportes adjuntos si faltan. Eso importa en plataformas
    sin disco persistente: la base de datos conserva las filas, pero el disco
    se borra en cada reinicio y las vistas previas quedarían rotas.
    """
    if os.getenv("SEMBRAR_DEMO_AL_ARRANCAR", "").strip().lower() not in {"1", "true", "si", "sí"}:
        return
    from sqlmodel import Session

    import semilla_demo
    from database import engine

    with Session(engine) as session:
        contador = semilla_demo._contador_demo(session)
        if contador is None:
            semilla_demo.cargar_demo(session)
        else:
            semilla_demo.asegurar_adjuntos_demo(session, contador.id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    crear_tablas()
    _sembrar_demo_si_corresponde()
    yield


app = FastAPI(
    title="App de Conciliación de Renta — API",
    description="Backend del proyecto de Ingeniería de Software (UAN).",
    version="0.7.0",
    lifespan=lifespan,
)

# Prefijo bajo el que se montan las rutas de la API.
#
# En desarrollo vale "" y todo queda como siempre (las 195 pruebas llaman a
# /contribuyentes, /cartera, ...). En el contenedor de producción vale "/api",
# porque el SPA se sirve en el mismo origen y sus rutas de vue-router
# (/cartera, /contribuyentes/3/resumen) chocarían con las de la API.
# Si se cambia, hay que construir el frontend con el mismo valor en
# VITE_API_URL: el Dockerfile y docker-compose.yml ya lo hacen.
PREFIJO_API = os.getenv("PREFIJO_API", "").rstrip("/")

app.add_middleware(AuditoriaMiddleware)


@app.middleware("http")
async def cabeceras_de_seguridad(request, call_next):
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "no-referrer")
    respuesta.headers.setdefault("Cache-Control", "no-store")
    return respuesta


app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_PERMITIDOS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition", "Retry-After"],
)

for _router in (
    router_contadores,
    router_contribuyentes,
    router_exogena,
    router_parametros,
    router_conciliacion,
    router_inventario,
    router_movimientos,
    router_reportes,
    router_cartera,
    router_adjuntos,
    router_auditoria,
):
    app.include_router(_router, prefix=PREFIJO_API)

# Endpoint de reinicio de la demo: solo existe si se define DEMO_RESET_TOKEN.
if os.getenv("DEMO_RESET_TOKEN"):
    from modulos.demo.router import router as router_demo

    app.include_router(router_demo, prefix=PREFIJO_API)


@app.get("/salud", tags=["sistema"])
def salud():
    return {"estado": "ok"}


# ---------------------------------------------------------------------------
# Frontend compilado (despliegue en un solo contenedor)
#
# En desarrollo el SPA lo sirve Vite en el puerto 5173 y esta parte no hace
# nada. En el contenedor de producción, el build de Vue queda en
# ESTATICOS_SPA (por defecto backend/static) y FastAPI lo sirve en la misma
# URL que la API: una sola dirección, sin CORS y sin un segundo servicio.
# ---------------------------------------------------------------------------

_DIRECTORIO_BASE = os.path.dirname(os.path.abspath(__file__))
ESTATICOS_SPA = os.path.abspath(
    os.path.join(_DIRECTORIO_BASE, os.getenv("ESTATICOS_SPA", "static"))
)


class _SpaStaticFiles(StaticFiles):
    """StaticFiles que devuelve index.html cuando la ruta no es un archivo.

    Sin esto, recargar la página en /contribuyentes/3 da 404: el servidor
    busca un archivo con ese nombre en vez de dejar que vue-router resuelva
    la ruta en el navegador.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return FileResponse(os.path.join(self.directory, "index.html"))
            raise


if os.path.isdir(ESTATICOS_SPA):
    app.mount(
        "/", _SpaStaticFiles(directory=ESTATICOS_SPA, html=True), name="spa"
    )
