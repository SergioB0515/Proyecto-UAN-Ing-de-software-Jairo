#!/usr/bin/env python3
"""Comprueba que las revisiones de Alembic y los modelos no se hayan separado.

Qué hace
--------
Crea una base vacía, le aplica `alembic upgrade head` y compara el esquema
resultante contra el metadata de SQLModel. Si sobra o falta algo, falla y dice
qué.

Por qué hace falta
------------------
Alembic no obliga a nada por sí solo. Si alguien agrega un campo a un modelo y
no escribe la revisión, la aplicación sigue funcionando en su máquina —donde
la base se creó entera de una vez— y se rompe en el despliegue, que es donde
el esquema viene de las revisiones. Es el mismo defecto que ya apareció dos
veces en este proyecto, con otra herramienta.

Sin esta comprobación, Alembic es ceremonia: archivos que nadie verifica.

Uso
---
    DATABASE_URL=postgresql://usuario@host:puerto/base \\
      herramientas/comprobar_revisiones.py

Trabaja sobre una base aparte, con el nombre de la que se le pasa más
`_revisiones`, y la borra al terminar. No toca la base que se le indica.

Con `--solo-comparar` no crea nada: compara contra los modelos el esquema de
la base que se le indica, tal como está. Así lo usa la prueba de
actualización, para comprobar que una base migrada quedó igual que una
construida desde cero.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BACKEND = RAIZ / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


def comparar(entorno: dict) -> int:
    """Compara contra los modelos el esquema de la base que indique el entorno."""
    resultado = subprocess.run(
        [sys.executable, "-c", _COMPARADOR],
        cwd=BACKEND,
        env=entorno,
        capture_output=True,
        text=True,
    )
    print(resultado.stdout, end="")
    if resultado.returncode != 0:
        print(resultado.stderr, file=sys.stderr)
    return resultado.returncode


def main() -> int:
    url_original = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url_original:
        print("Hace falta DATABASE_URL (o TEST_DATABASE_URL).", file=sys.stderr)
        return 2

    if "--solo-comparar" in sys.argv:
        print("==> Comparando el esquema de la base con los modelos")
        return comparar({**os.environ, "DATABASE_URL": url_original})

    url = make_url(url_original)
    nombre = f"{url.database}_revisiones"
    url_servidor = url.set(database="postgres")
    url_prueba = url.set(database=nombre)

    servidor = create_engine(url_servidor, isolation_level="AUTOCOMMIT")
    with servidor.connect() as conexion:
        conexion.execute(text(f'DROP DATABASE IF EXISTS "{nombre}"'))
        conexion.execute(text(f'CREATE DATABASE "{nombre}"'))
    print(f"==> Base vacía: {nombre}")

    try:
        entorno = {**os.environ, "DATABASE_URL": url_prueba.render_as_string(hide_password=False)}
        print("==> alembic upgrade head")
        resultado = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=entorno,
            capture_output=True,
            text=True,
        )
        if resultado.returncode != 0:
            print(resultado.stdout)
            print(resultado.stderr, file=sys.stderr)
            return 1

        print("==> Comparando el esquema con los modelos")
        if comparar(entorno) != 0:
            return 1
    finally:
        with servidor.connect() as conexion:
            conexion.execute(text(f'DROP DATABASE IF EXISTS "{nombre}"'))

    print("==> Las revisiones reproducen el esquema de los modelos.")
    return 0


# Se corre en un proceso aparte porque `database.py` crea el motor al
# importarse, con la URL que haya en el entorno en ese momento.
_COMPARADOR = """
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlmodel import SQLModel

from database import engine, registrar_modelos

registrar_modelos()
with engine.connect() as conexion:
    contexto = MigrationContext.configure(conexion, opts={"compare_type": True})
    diferencias = compare_metadata(contexto, SQLModel.metadata)

if diferencias:
    print("Las revisiones no reproducen los modelos. Diferencias:")
    for d in diferencias:
        print("  -", d)
    print()
    print("Si cambiaste un modelo, falta la revisión:")
    print("  cd backend && alembic revision --autogenerate -m 'lo que cambiaste'")
    raise SystemExit(1)
print("Sin diferencias.")
"""


if __name__ == "__main__":
    raise SystemExit(main())
