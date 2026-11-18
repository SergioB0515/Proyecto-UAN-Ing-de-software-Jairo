# Backend

FastAPI + SQLModel + PostgreSQL. Razones del stack en
[../documentacion/04-arquitectura.md](../documentacion/04-arquitectura.md).

| Incremento | Historias | Módulos |
|---|---|---|
| 1 | HU-01 a HU-04 | `contadores`, `contribuyentes` |
| 2 | HU-05 a HU-07 | `exogena`, `parametros` |
| 3 | HU-08 a HU-10 | `conciliacion` |
| 4 | HU-11 a HU-14 | `inventario`, `movimientos` |
| 5 | HU-15 a HU-18 | `reportes`, `cartera` |
| 6 | HU-19 a HU-21 | `auditoria`, `contadores` |
| 7 | HU-22 a HU-24 | `contribuyentes` |
| 8 | HU-25 a HU-27 | `parametros`, `contribuyentes`, `cartera` |
| Extra | — | `adjuntos`, `liquidacion`, `gestion`, cruce con la DIAN en `conciliacion` |

## Endpoints

Todos salvo registro, login y `/salud` exigen `Authorization: Bearer <token>`
y filtran por el contador del token.

| Método y ruta | HU |
|---|---|
| `POST /contadores/registro`, `POST /contadores/login`, `GET /contadores/yo` | HU-01 |
| `POST/GET /contribuyentes`, `GET/PATCH/DELETE /contribuyentes/{id}` | HU-02 |
| `POST/GET /contribuyentes/{id}/fuentes-ingreso?periodo_fiscal_id=`, `PATCH/DELETE .../fuentes-ingreso/{fid}` | HU-03 |
| `POST/GET /contribuyentes/{id}/activos?periodo_fiscal_id=`, `PATCH/DELETE .../activos/{aid}`, `GET /contribuyentes/{id}/patrimonio?periodo_fiscal_id=` | HU-04 |
| `POST/GET /contribuyentes/{id}/periodos-fiscales` | — |
| `POST /contribuyentes/{id}/periodos-fiscales/{pid}/exogena` (multipart, campo `archivo`) | HU-05 |
| `GET /contribuyentes/{id}/reportes-exogena`, `.../{rid}/topes`, `.../{rid}/registros?concepto_code=&nit_reportante=` | HU-06 |
| `POST/GET /parametros/umbrales`, `POST /parametros/umbrales/oficiales/{anio}`, `GET /parametros/contribuyentes/{id}/periodos-fiscales/{pid}/obligacion` | HU-07 |
| `GET /contribuyentes/{id}/periodos-fiscales/{pid}/conciliacion` | HU-08, HU-09 |
| `GET /contribuyentes/{id}/periodos-fiscales/{pid}/cruce-dian` (ver [modulos/conciliacion](modulos/conciliacion/README.md)) | — |
| `GET /contribuyentes/{id}/periodos-fiscales/{pid}/borrador-renglones` | HU-10 |
| `POST/GET /contribuyentes/{id}/categorias`, `DELETE .../categorias/{cid}` | HU-11 |
| `POST/GET /contribuyentes/{id}/productos`, `GET/PATCH .../productos/{prid}` | HU-11 |
| `POST/GET /contribuyentes/{id}/documentos-soporte`, `POST/GET /contribuyentes/{id}/movimientos` | HU-12 |
| `POST/GET /contribuyentes/{id}/proveedores` | HU-13 |
| `GET /contribuyentes/{id}/productos/{prid}/kardex`, `GET /contribuyentes/{id}/periodos-fiscales/{pid}/costo-ventas` | HU-14 |
| `POST /contribuyentes/{id}/periodos-fiscales/{pid}/cerrar`, `POST .../reabrir` | HU-15 |
| `GET /contribuyentes/{id}/periodos-fiscales/{pid}/kardex`, `GET .../reportes/{tipo}?formato=xlsx\|pdf` (`tipo`: `kardex`, `saldo-inventario`, `conciliacion`, `borrador-renglones`, `resumen`) | HU-16 |
| `GET /contribuyentes/{id}/periodos-fiscales/{pid}/resumen` | HU-17 |
| `GET /cartera?anio_gravable=&orden=alertas\|nombre` | HU-18 |
| `PUT /contadores/yo/contrasena` | HU-20 |
| `GET /auditoria?contribuyente_id=`, `GET /auditoria/accesos` | HU-19, HU-21 |
| `POST /contribuyentes/{id}/periodos-fiscales/{pid}/copiar-activos` | HU-23 |
| `GET/PUT /parametros/plazos/{anio}`, `POST /parametros/plazos/{anio}/calendario-oficial` | HU-25 |
| `PATCH /contribuyentes/{id}/periodos-fiscales/{pid}` (`fecha_presentacion`, `fecha_vencimiento_manual`) | HU-26 |
| `GET /cartera?orden=vencimiento`, `GET /cartera/exportar?formato=xlsx\|pdf` | HU-25, HU-27 |
| `GET /liquidacion/cedulas`, `GET/PATCH /liquidacion/contribuyentes/{id}/periodos-fiscales/{pid}/hoja`, `POST/GET/DELETE .../deducciones`, `GET/PUT .../ingresos`, `GET /liquidacion/contribuyentes/{id}/periodos-fiscales/{pid}`, `GET .../exportar?formato=xlsx\|pdf`, `GET/PUT/DELETE .../depreciacion`, `GET/POST/DELETE .../pagos-efectivo`, `GET/POST/DELETE /liquidacion/contribuyentes/{id}/perdidas`, `GET /liquidacion/categorias-depreciacion`, `GET .../plantillas-deducciones`, `POST .../deducciones/desde-plantilla`, `POST .../hoja/copiar-del-anterior`, `GET .../formulario-210`, `GET .../escenarios`, `GET/POST/DELETE .../ventas-inmuebles` (ver [modulos/liquidacion](modulos/liquidacion/README.md)) | — |
| `GET .../periodos-fiscales/{pid}/gestion`, `PATCH .../gestion/seguimiento`, `POST .../gestion/presentaciones`, `POST .../gestion/traer-del-anio-anterior`, `POST /contribuyentes/{id}/declaraciones-anteriores`, `GET/POST/PATCH .../documentos`, `GET .../informe-cliente`, `GET/PUT /tasas-interes-moratorio` (ver [modulos/gestion](modulos/gestion/README.md)) | — |
| `POST/GET /contribuyentes/{id}/adjuntos`, `GET .../adjuntos/resumen`, `GET/PATCH/DELETE .../adjuntos/{aid}`, `GET .../periodos-fiscales/{pid}/soportes/zip` (ver [modulos/adjuntos](modulos/adjuntos/README.md)) | — |

## Reglas

- Activos e ingresos llevan `periodo_fiscal_id`; con el periodo cerrado, 409.
  Sin él, los `GET` devuelven todos los años.
- El periodo de un registro no se cambia: se elimina y se registra en el año
  correcto. El activo `INVENTARIO` de un cierre se deshace reabriendo el año.
- Un contribuyente con años gravables o inventario no se elimina (409).

## Seguridad

- 5 intentos fallidos en 15 minutos: 429 con `Retry-After`.
- `AuditoriaMiddleware` registra las acciones de `ACCIONES_AUDITADAS`; una
  prueba falla si una ruta que modifica datos no está en la lista.
- Exógena: máx. `TAMANO_MAXIMO_EXOGENA_MB` (5) y firma de Excel (413 / 422).
- Adjuntos: firma real del archivo, máx. `TAMANO_MAXIMO_ADJUNTO_MB` (15),
  nombre generado por el servidor (415 / 413).
- CORS por `ORIGENES_PERMITIDOS`. Cabeceras `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store`.

## Códigos de error

| Código | Caso |
|---|---|
| 404 | No existe o es de otro contador (mismo código en ambos casos). |
| 409 | Conflicto de negocio: duplicado, stock, periodo cerrado. |
| 413 | Archivo demasiado grande. |
| 415 | Formato de soporte no admitido. |
| 422 | Datos inválidos. |
| 429 | Cuenta bloqueada. |

## Puesta en marcha

Python 3.11+ y PostgreSQL.

```bash
python -m venv venv
source venv/bin/activate            # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt

psql -U postgres -c "CREATE DATABASE renta_db;"
psql -U postgres -c "CREATE DATABASE renta_test_db;"

cp .env.example .env                # definir JWT_SECRET_KEY y DATABASE_URL
uvicorn main:app --reload           # docs en http://127.0.0.1:8000/docs
pytest
```

- Las pruebas usan PostgreSQL real (`renta_test_db`, o `TEST_DATABASE_URL`);
  cada prueba revierte su transacción.
- CI: `.github/workflows/ci.yml` corre las pruebas y el build del frontend.
- Sin Alembic: `crear_tablas` crea tablas nuevas y `database.py` agrega las
  columnas posteriores al arrancar (idempotente).
