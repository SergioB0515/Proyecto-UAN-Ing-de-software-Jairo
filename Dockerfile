# Imagen única: compila el SPA de Vue y lo sirve desde el mismo FastAPI.
#
# Un solo contenedor significa una sola URL, sin CORS y sin un segundo
# servicio que mantener. Y lo que corre en el servidor es exactamente lo
# mismo que corre en el portátil con `docker compose up`.

# --------------------------------------------------------------------------
# Etapa 1 — build del frontend
# --------------------------------------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# El SPA se sirve en el mismo origen que la API, bajo el prefijo /api: sin él,
# las rutas de vue-router (/cartera, /contribuyentes/3) chocan con las de la
# API. Debe coincidir con PREFIJO_API del backend, y no puede ir vacío:
# src/api/cliente.js cae a 127.0.0.1:8000 si VITE_API_URL es falsy.
ENV VITE_API_URL=/api
RUN npm run build

# --------------------------------------------------------------------------
# Etapa 2 — runtime
# --------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /app/dist ./static

# Debe coincidir con el VITE_API_URL con el que se construyó el SPA arriba.
ENV PREFIJO_API=/api

# Los adjuntos (recibos, capturas, PDF) se guardan en disco. En compose esta
# carpeta es un volumen; en un PaaS sin disco persistente se pierden en cada
# despliegue (ver despliegue/README.md).
ENV ALMACEN_ADJUNTOS=/datos/almacen
RUN mkdir -p /datos/almacen \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app /datos
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=4).status==200 else 1)"

# $PORT lo define el proveedor (Render, Railway); en local cae a 8000.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
