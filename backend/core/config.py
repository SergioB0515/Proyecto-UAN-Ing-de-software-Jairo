import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/renta_db"
)

# Algunos proveedores (Render entre ellos) entregan la cadena de conexión con
# el esquema antiguo «postgres://», que SQLAlchemy 2.x rechaza con
# NoSuchModuleError. Normalizarlo aquí evita un fallo de arranque que desde
# los logs parece un error de credenciales.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRACION_MINUTOS = int(os.getenv("JWT_EXPIRACION_MINUTOS", "60"))

ORIGENES_PERMITIDOS = [
    origen.strip()
    for origen in os.getenv(
        "ORIGENES_PERMITIDOS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origen.strip()
]

TAMANO_MAXIMO_EXOGENA_MB = float(os.getenv("TAMANO_MAXIMO_EXOGENA_MB", "5"))

TAMANO_MAXIMO_ADJUNTO_MB = float(os.getenv("TAMANO_MAXIMO_ADJUNTO_MB", "15"))

_DIRECTORIO_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ALMACEN_ADJUNTOS = os.path.abspath(
    os.path.join(_DIRECTORIO_BACKEND, os.getenv("ALMACEN_ADJUNTOS", "almacen"))
)

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY no está definido. Copia backend/.env.example a "
        "backend/.env y define un valor propio (ver instrucciones en ese "
        "archivo) antes de arrancar la aplicación."
    )
