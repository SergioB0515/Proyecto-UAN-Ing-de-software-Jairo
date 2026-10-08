"""Configuración de la aplicación, leída de variables de entorno.

Copia `.env.example` a `.env` y ajusta los valores para tu máquina antes de
arrancar el servidor o correr las pruebas — ver ese archivo para el detalle
de cada variable.
"""
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/renta_db"
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRACION_MINUTOS = int(os.getenv("JWT_EXPIRACION_MINUTOS", "60"))

# Orígenes del frontend autorizados por CORS, separados por coma. En
# producción, el dominio real donde se publique el frontend.
ORIGENES_PERMITIDOS = [
    origen.strip()
    for origen in os.getenv(
        "ORIGENES_PERMITIDOS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origen.strip()
]

# Tamaño máximo del archivo de exógena (el de la DIAN pesa unos pocos KB).
TAMANO_MAXIMO_EXOGENA_MB = float(os.getenv("TAMANO_MAXIMO_EXOGENA_MB", "5"))

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY no está definido. Copia backend/.env.example a "
        "backend/.env y define un valor propio (ver instrucciones en ese "
        "archivo) antes de arrancar la aplicación."
    )
