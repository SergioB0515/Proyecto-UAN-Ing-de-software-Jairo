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
from modulos.gestion.router import router as router_gestion
from modulos.inventario.router import router as router_inventario
from modulos.liquidacion.router import router as router_liquidacion
from modulos.movimientos.router import router as router_movimientos
from modulos.parametros.router import router as router_parametros
from modulos.reportes.router import router as router_reportes


def _sembrar_demo_si_corresponde() -> None:
    """Siembra la demo al arrancar si SEMBRAR_DEMO_AL_ARRANCAR=1.
    En arranques siguientes solo regenera los adjuntos que falten.
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

# Prefijo de la API. "" en desarrollo; "/api" en el contenedor, donde el SPA
# comparte origen. Debe coincidir con VITE_API_URL del build.
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
    router_liquidacion,
    router_gestion,
    router_movimientos,
    router_reportes,
    router_cartera,
    router_adjuntos,
    router_auditoria,
):
    app.include_router(_router, prefix=PREFIJO_API)

# Reinicio de la demo: solo con DEMO_RESET_TOKEN definido.
if os.getenv("DEMO_RESET_TOKEN"):
    from modulos.demo.router import router as router_demo

    app.include_router(router_demo, prefix=PREFIJO_API)


@app.get("/salud", tags=["sistema"])
def salud():
    return {"estado": "ok"}


# Frontend compilado. En el contenedor, el build de Vue (ESTATICOS_SPA) se
# sirve desde FastAPI en el mismo origen. En desarrollo lo sirve Vite.

_DIRECTORIO_BASE = os.path.dirname(os.path.abspath(__file__))
ESTATICOS_SPA = os.path.abspath(
    os.path.join(_DIRECTORIO_BASE, os.getenv("ESTATICOS_SPA", "static"))
)


class _SpaStaticFiles(StaticFiles):
    """StaticFiles que devuelve index.html si la ruta no es un archivo (vue-router)."""

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
