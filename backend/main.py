"""Punto de entrada de la API. Arrancar con:
    uvicorn main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import ORIGENES_PERMITIDOS
from database import crear_tablas
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    crear_tablas()
    yield


app = FastAPI(
    title="App de Conciliación de Renta — API",
    description="Backend del proyecto de Ingeniería de Software (UAN).",
    version="0.7.0",
    lifespan=lifespan,
)

# Orden: el último agregado es el más externo. CORS va por fuera para que
# también las respuestas de error lleven sus cabeceras.
app.add_middleware(AuditoriaMiddleware)


@app.middleware("http")
async def cabeceras_de_seguridad(request, call_next):
    """Cabeceras defensivas en toda respuesta de la API: impiden que el
    navegador adivine tipos de contenido, que la API se incruste en un
    iframe y que se filtre la URL en el Referer."""
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "no-referrer")
    respuesta.headers.setdefault("Cache-Control", "no-store")
    return respuesta


app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_PERMITIDOS,
    allow_credentials=False,  # la API usa token Bearer, no cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition", "Retry-After"],
)

app.include_router(router_contadores)
app.include_router(router_contribuyentes)
app.include_router(router_exogena)
app.include_router(router_parametros)
app.include_router(router_conciliacion)
app.include_router(router_inventario)
app.include_router(router_movimientos)
app.include_router(router_reportes)
app.include_router(router_cartera)
app.include_router(router_auditoria)


@app.get("/salud", tags=["sistema"])
def salud():
    """Chequeo simple de que la API está arriba — útil para despliegue."""
    return {"estado": "ok"}
