# Imagen única: compila el SPA y lo sirve desde FastAPI.

# Etapa 1 — build del frontend
FROM node:26-alpine AS frontend

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Debe coincidir con PREFIJO_API. No vacío: cliente.js usaría 127.0.0.1:8000.
ENV VITE_API_URL=/api
RUN npm run build

# Etapa 2 — runtime
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# La imagen oficial se reconstruye cada tanto; los parches de Debian salen
# antes. Sin esto la imagen arrastra lo que ya tiene arreglo (Trivy lo vigila
# en .github/workflows/seguridad.yml).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /app/dist ./static

# Igual a VITE_API_URL.
ENV PREFIJO_API=/api

# Adjuntos en disco (volumen en compose).
ENV ALMACEN_ADJUNTOS=/datos/almacen
RUN mkdir -p /datos/almacen \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app /datos
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=4).status==200 else 1)"

# $PORT del proveedor; 8000 por defecto.
# --no-proxy-headers: uvicorn no toca la IP del cliente. Cuánto confiar en
# X-Forwarded-For lo decide la app con PROXIES_CONFIABLES (core/red.py).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers"]
