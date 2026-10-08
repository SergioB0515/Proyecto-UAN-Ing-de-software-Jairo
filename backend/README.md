# Backend — API de Conciliación de Renta

FastAPI + SQLModel sobre PostgreSQL. Ver
[../documentacion/04-arquitectura.md](../documentacion/04-arquitectura.md)
para las razones de cada elección técnica.

**Estado**: incrementos 1 a 4 implementados y probados — **86/86 pruebas**.

| Incremento | Historias | Módulos |
|---|---|---|
| 1 | HU-01 a HU-04 | `contadores`, `contribuyentes` |
| 2 | HU-05 a HU-07 | `exogena`, `parametros` |
| 3 | HU-08 a HU-10 | `conciliacion` |
| 4 | HU-11 a HU-14 | `inventario`, `movimientos` |
| 5 | HU-15 a HU-18 | `reportes`, `cartera` — pendiente |

## Endpoints principales

Todos (salvo registro, login y `/salud`) exigen `Authorization: Bearer <token>`
y filtran por el contador del token.

| Método y ruta | HU |
|---|---|
| `POST /contadores/registro`, `POST /contadores/login`, `GET /contadores/yo` | HU-01 |
| `POST/GET /contribuyentes` | HU-02 |
| `POST/GET /contribuyentes/{id}/fuentes-ingreso` | HU-03 |
| `POST/GET /contribuyentes/{id}/activos`, `GET /contribuyentes/{id}/patrimonio` | HU-04 |
| `POST/GET /contribuyentes/{id}/periodos-fiscales` | — |
| `POST /contribuyentes/{id}/periodos-fiscales/{pid}/exogena` (multipart, campo `archivo`) | HU-05 |
| `GET /contribuyentes/{id}/reportes-exogena`, `.../{rid}/topes`, `.../{rid}/registros?concepto_code=&nit_reportante=` | HU-06 |
| `POST/GET /parametros/umbrales`, `GET /parametros/contribuyentes/{id}/periodos-fiscales/{pid}/obligacion` | HU-07 |
| `GET /contribuyentes/{id}/periodos-fiscales/{pid}/conciliacion` | HU-08, HU-09 |
| `GET /contribuyentes/{id}/periodos-fiscales/{pid}/borrador-renglones` | HU-10 |
| `POST/GET /contribuyentes/{id}/categorias`, `DELETE .../categorias/{cid}` | HU-11 |
| `POST/GET /contribuyentes/{id}/productos`, `GET/PATCH .../productos/{prid}` | HU-11 |
| `POST/GET /contribuyentes/{id}/documentos-soporte`, `POST/GET /contribuyentes/{id}/movimientos` | HU-12 |
| `POST/GET /contribuyentes/{id}/proveedores` | HU-13 |
| `GET /contribuyentes/{id}/productos/{prid}/kardex`, `GET /contribuyentes/{id}/periodos-fiscales/{pid}/costo-ventas` | HU-14 |

Códigos de error: `404` si el recurso no existe o es de otro contador
(deliberadamente el mismo código en ambos casos), `409` para conflictos de
negocio (duplicados, stock insuficiente, periodo cerrado, contribuyente
asalariado en inventario) y `422` para datos inválidos.

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

## Qué falta (Incremento 5)

`reportes` (cierre de `PeriodoFiscal`, kardex y reportes exportables en
Excel/PDF) y `cartera` (panel consolidado) todavía son solo la carpeta y su
`README.md`. Las piezas que necesitan ya existen: el costo de ventas expone
`total_inventario_final` (el valor que el cierre llevará al patrimonio como
`Activo` de tipo `INVENTARIO`), la conciliación expone `resumen.NO_DECLARADO`
(las alertas del panel de cartera), y la importación de exógena y el
registro de movimientos ya rechazan periodos `CERRADO`.

**Nota sobre el esquema**: sin Alembic, `crear_tablas` crea las tablas
nuevas pero no altera las existentes. Este incremento solo agrega tablas
(`proveedores`, `documentos_soporte`, `movimientos`), así que una base de
datos de desarrollo creada antes sigue funcionando sin recrearla.
