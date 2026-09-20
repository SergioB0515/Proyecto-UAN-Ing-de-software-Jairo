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

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY no está definido. Copia backend/.env.example a "
        "backend/.env y define un valor propio (ver instrucciones en ese "
        "archivo) antes de arrancar la aplicación."
    )
