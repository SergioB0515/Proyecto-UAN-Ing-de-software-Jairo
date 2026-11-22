"""Configuración de Alembic para este proyecto.

Dos diferencias con la plantilla que genera `alembic init`:

- La URL de la base no se escribe en `alembic.ini`. Sale de `core.config`,
  que es de donde la toma la aplicación: así no hay dos sitios donde
  configurar lo mismo, ni riesgo de migrar una base distinta de la que se
  está usando.
- `target_metadata` se arma después de `registrar_modelos()`. Los modelos
  viven en los módulos y SQLModel solo los conoce cuando se importan; sin esa
  llamada, `--autogenerate` vería un esquema vacío y propondría borrar todas
  las tablas.
"""

from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

from core.config import DATABASE_URL
from database import engine, registrar_modelos

config = context.config

# La aplicación llama a Alembic al arrancar; ahí ya configuró su registro de
# eventos y no queremos que esto lo reemplace. Desde la línea de órdenes sí.
if config.config_file_name is not None and config.attributes.get(
    "configurar_registro", True
):
    fileConfig(config.config_file_name)

registrar_modelos()
target_metadata = SQLModel.metadata

# `compare_type` detecta un cambio de tipo de columna, no solo de nombre. Hace
# falta para la migración de dinero de `float` a `NUMERIC(18,2)`: sin esto,
# `--autogenerate` no vería la diferencia.
#
# `compare_server_default` queda apagado a propósito. Las migraciones a mano
# que trajo el proyecto hasta aquí agregaron columnas con DEFAULT en la base
# (`NOT NULL DEFAULT 0`) para poder poblarlas sin romper las filas que ya
# existían, y esos valores por omisión no están declarados en los modelos.
# Encendido, el comparador los reportaría como diferencia en cada corrida y la
# comprobación de deriva no volvería a servir para nada.
OPCIONES = {
    "target_metadata": target_metadata,
    "compare_type": True,
}


def correr_sin_conexion() -> None:
    """Genera el SQL sin tocar la base, para revisarlo antes de aplicarlo."""
    context.configure(
        url=DATABASE_URL,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **OPCIONES,
    )
    with context.begin_transaction():
        context.run_migrations()


def correr_con_conexion() -> None:
    with engine.connect() as conexion:
        context.configure(connection=conexion, **OPCIONES)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    correr_sin_conexion()
else:
    correr_con_conexion()
