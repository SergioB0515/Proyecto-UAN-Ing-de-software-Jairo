# Backend — API de Conciliación de Renta

FastAPI + SQLModel sobre PostgreSQL. Ver
[../documentacion/04-arquitectura.md](../documentacion/04-arquitectura.md)
para las razones de cada elección técnica.

**Estado**:
- **Incremento 1** (HU-01 a HU-04): implementado y probado — 17/17.
- **Incremento 2** (HU-05 a HU-07): estructura completa (modelos, routers,
  tests, catálogo, umbrales) — pero **`parsear_archivo_exogena` y
  `verificar_obligacion_declarar` están sin implementar a propósito**.
  Sus firmas y docstrings están en `modulos/exogena/servicios.py` y
  `modulos/parametros/servicios.py`; los tests que definen el objetivo a
  cumplir están en `tests/test_exogena.py` y `tests/test_parametros.py`.
  Con el esqueleto tal como está: **18 pruebas pasan, 20 fallan por
  `NotImplementedError`** (ninguna por error de estructura). Cuando
  implementes las dos funciones, las 20 deberían pasar sin tocar nada
  más.

## Requisitos

- Python 3.11 o superior
- PostgreSQL corriendo localmente (o accesible por red)

## Puesta en marcha

**1. Crear y activar el entorno virtual**

En Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

En Linux/macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

**2. Instalar dependencias**
```bash
pip install -r requirements.txt
```

**3. Crear las bases de datos**

Con PostgreSQL corriendo y accesible como el usuario `postgres`:
```bash
psql -U postgres -c "CREATE DATABASE renta_db;"
psql -U postgres -c "CREATE DATABASE renta_test_db;"
```
(`renta_db` es la de desarrollo; `renta_test_db` la usan las pruebas —
ver `tests/conftest.py`. Los nombres y credenciales son ajustables por
variable de entorno, ver el siguiente paso.)

**4. Configurar las variables de entorno**
```bash
cp .env.example .env
```
Edita `.env` y define tu propio `JWT_SECRET_KEY` (el archivo trae el
comando para generar uno). Ajusta `DATABASE_URL` si tu usuario, contraseña
o puerto de PostgreSQL son distintos a los del ejemplo.

**5. Arrancar el servidor**
```bash
uvicorn main:app --reload
```
Las tablas se crean automáticamente al arrancar (`database.crear_tablas`,
sin Alembic en este incremento — ver la nota en `database.py`). La
documentación interactiva queda en `http://127.0.0.1:8000/docs`.

**6. Correr las pruebas**
```bash
pytest -v
```
Las pruebas corren contra `renta_test_db` con una base de datos real (no
mocks): cada prueba abre una transacción y la revierte al terminar, así
que no hace falta limpiar datos entre corridas. Si quieres apuntar las
pruebas a otra base, define `TEST_DATABASE_URL` antes de correr `pytest`.

## Qué falta (próximos incrementos)

`parametros`, `exogena`, `conciliacion`, `cartera`, `inventario`,
`movimientos` y `reportes` todavía son solo la carpeta y el `README.md`
de intención (ver [../documentacion/05-modelo-desarrollo.md](../documentacion/05-modelo-desarrollo.md)
para el orden). El Incremento 2 (importación de exógena + verificación de
obligación de declarar) es el siguiente.
