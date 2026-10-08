"""Punto de entrada de la API. Arrancar con:
    uvicorn main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import crear_tablas
from modulos.conciliacion.router import router as router_conciliacion
from modulos.contadores.router import router as router_contadores
from modulos.contribuyentes.router import router as router_contribuyentes
from modulos.exogena.router import router as router_exogena
from modulos.inventario.router import router as router_inventario
from modulos.movimientos.router import router as router_movimientos
from modulos.parametros.router import router as router_parametros

# Orígenes del frontend en desarrollo (Vite). En producción, reemplazar por
# el dominio real desplegado.
ORIGENES_PERMITIDOS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    crear_tablas()
    yield


app = FastAPI(
    title="App de Conciliación de Renta — API",
    description="Backend del proyecto de Ingeniería de Software (UAN).",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_PERMITIDOS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router_contadores)
app.include_router(router_contribuyentes)
app.include_router(router_exogena)
app.include_router(router_parametros)
app.include_router(router_conciliacion)
app.include_router(router_inventario)
app.include_router(router_movimientos)


@app.get("/salud", tags=["sistema"])
def salud():
    """Chequeo simple de que la API está arriba — útil para despliegue."""
    return {"estado": "ok"}
