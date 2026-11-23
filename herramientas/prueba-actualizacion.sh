#!/usr/bin/env bash
#
# Prueba de actualización del esquema.
#
# Comprueba que una base creada con el código anterior siga sirviendo después
# de migrarla con el código actual. Es decir: hace lo que hace un despliegue.
#
# Por qué hace falta
# ------------------
# El CI normal levanta un contenedor de Postgres nuevo en cada corrida, así
# que la base nace vacía y el esquema se crea completo de una vez. En una base
# recién creada los defectos de migración NO EXISTEN, y los dos que llegaron a
# producción eran justo de esa familia:
#
#   1. `create_all` no agrega columnas a una tabla que ya existe.
#   2. `create_all` tampoco agrega valores a un tipo ENUM que ya existe.
#
# Las pruebas no se equivocaron: estaban contestando otra pregunta. Prueban
# muy bien una instalación nueva y no prueban en absoluto una actualización.
#
# Por qué la suite sirve de verificación
# --------------------------------------
# `tests/conftest.py` crea el esquema con `create_all`, que no toca una tabla
# que ya existe. Así que si después de migrar falta una columna o un valor de
# enum, las pruebas fallan igual que falló producción. No hay que escribir
# una aserción por defecto posible: basta con correr la suite sobre una base
# que vino del código anterior.
#
# Se siembran los datos demo con el código anterior antes de migrar, porque
# sobre una tabla vacía casi cualquier migración pasa: una columna NOT NULL
# sin valor por omisión solo falla si hay filas. Después de migrar se leen y
# se borran con el código nuevo, que de paso comprueba que el código actual
# entiende los datos que escribió el anterior.
#
# Uso:
#   TEST_DATABASE_URL=postgresql://usuario@host:puerto/base \
#     herramientas/prueba-actualizacion.sh [ref-base]
#
# `ref-base` es el código que hace de «producción». Por omisión origin/main,
# que es lo que está desplegado.

set -euo pipefail

REF_BASE="${1:-origin/main}"
: "${TEST_DATABASE_URL:?hace falta TEST_DATABASE_URL}"

export DATABASE_URL="$TEST_DATABASE_URL"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-clave-solo-para-la-prueba}"
PY="${PYTHON:-$(command -v python3 || command -v python)}"

RAIZ="$(git rev-parse --show-toplevel)"
cd "$RAIZ"

# Un ref que no existe, o que es el commit actual, no sirve de base. Pasa con
# `github.event.before` en el primer push de una rama, que llega en ceros.
if ! git rev-parse --verify --quiet "${REF_BASE}^{commit}" >/dev/null; then
    REF_BASE=origin/main
fi
if [ "$(git rev-parse "$REF_BASE")" = "$(git rev-parse HEAD)" ]; then
    REF_BASE="$(git rev-parse 'HEAD^')"
fi

TEMPORAL="$(mktemp -d)"
ARBOL="$TEMPORAL/base"
export ALMACEN_ADJUNTOS="$TEMPORAL/almacen"
mkdir -p "$ALMACEN_ADJUNTOS"

limpiar() {
    git worktree remove --force "$ARBOL" >/dev/null 2>&1 || true
    rm -rf "$TEMPORAL"
}
trap limpiar EXIT

echo "==> Base de partida: $REF_BASE ($(git log -1 --format=%s "$REF_BASE"))"
git worktree add --detach --quiet "$ARBOL" "$REF_BASE"

# El código anterior corre con SUS dependencias, no con las del commit actual.
# Si un commit cambia de librería (python-jose -> PyJWT, por ejemplo), el
# código de producción no la puede importar y la prueba falla por algo que en
# un despliegue real no pasa: allá cada versión trae sus dependencias.
PY_BASE="$PY"
if ! cmp -s "$ARBOL/backend/requirements.txt" backend/requirements.txt; then
    echo "==> Las dependencias cambiaron: entorno aparte para el código anterior"
    "$PY" -m venv "$TEMPORAL/venv-base"
    PY_BASE="$TEMPORAL/venv-base/bin/python"
    [ -x "$PY_BASE" ] || PY_BASE="$TEMPORAL/venv-base/Scripts/python.exe"
    "$PY_BASE" -m pip install --quiet -r "$ARBOL/backend/requirements.txt"
fi

echo "==> Creando el esquema con el código anterior"
(cd "$ARBOL/backend" && "$PY_BASE" -c "from database import crear_tablas; crear_tablas()")

echo "==> Sembrando datos con el código anterior"
(cd "$ARBOL/backend" && "$PY_BASE" semilla_demo.py >/dev/null)

echo "==> Migrando con el código actual"
(cd backend && "$PY" -c "from database import crear_tablas; crear_tablas()")

# La comprobación directa: la base migrada tiene que quedar igual que una
# construida desde cero con las revisiones. Si el puente a Alembic no alcanza
# el baseline, o si falta una revisión, se ve acá y con el nombre de lo que
# falta, en vez de como una prueba rara que falla más abajo.
echo "==> Comparando el esquema migrado con los modelos"
herramientas/comprobar_revisiones.py --solo-comparar

echo "==> Leyendo y borrando con el código actual los datos del anterior"
(cd backend && "$PY" -c "
from sqlmodel import Session

from database import engine
from semilla_demo import borrar_demo

with Session(engine) as sesion:
    if not borrar_demo(sesion):
        raise SystemExit(
            'El código actual no encontró los datos que sembró el anterior.'
        )
    sesion.commit()
print('Datos anteriores leídos y borrados.')
")

# El esquema tiene que venir de la actualización; los datos, no. `borrar_demo`
# borra lo del contador demo pero deja las tablas de parámetros fiscales, que
# son datos de referencia globales y en producción está bien que se queden. En
# la suite estorban: hay pruebas que siembran sus propios parámetros y asumen
# que no hay otros. Se vacía todo y queda el esquema migrado, que es lo que
# esta prueba vino a verificar.
echo "==> Vaciando los datos y dejando el esquema migrado"
(cd backend && "$PY" -c "
from sqlalchemy import text
from sqlmodel import SQLModel

from database import engine, registrar_modelos

registrar_modelos()
tablas = ', '.join(f'\"{t}\"' for t in SQLModel.metadata.tables)
with engine.begin() as conexion:
    conexion.execute(text(f'TRUNCATE {tablas} RESTART IDENTITY CASCADE'))
print('Datos vaciados.')
")

echo "==> Suite completa sobre la base migrada"
(cd backend && "$PY" -m pytest -q)

echo "==> La actualización funciona."
