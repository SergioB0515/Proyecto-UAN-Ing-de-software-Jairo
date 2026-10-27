# modulos/adjuntos/

Soportes adjuntos (recibos, facturas, capturas, PDF de transferencias,
certificados…) de cualquier objeto de un contribuyente.

- `modelos.py`: tabla `Adjunto` (metadato y a qué objeto pertenece) y los
  esquemas de lectura. `entidad_tipo` + `entidad_id` identifican el objeto:
  `CONTRIBUYENTE`, `PERIODO_FISCAL`, `ACTIVO`, `FUENTE_INGRESO`,
  `DOCUMENTO_SOPORTE`, `MOVIMIENTO` o `PROVEEDOR`.
- `servicios.py`: validación, almacenamiento en disco, consultas y ZIP.
- `router.py`: endpoints bajo `/contribuyentes/{id}/adjuntos`.

Los archivos viven en `ALMACEN_ADJUNTOS` (por defecto `backend/almacen/`,
fuera de git) con un nombre generado por el servidor; la base solo guarda
el metadato. Respalda esa carpeta junto con la base de datos.

Endpoints:

| Ruta | Qué hace |
|---|---|
| `POST /contribuyentes/{id}/adjuntos` | Sube un archivo (multipart: `archivo`, `entidad_tipo`, `entidad_id`, `categoria`, `descripcion`). |
| `GET /contribuyentes/{id}/adjuntos` | Lista con filtros `entidad_tipo`, `entidad_id`, `periodo_fiscal_id` (+ `incluir_generales`), `categoria` y `q` (nombre o nota). |
| `GET /contribuyentes/{id}/adjuntos/resumen` | Cantidad de soportes por objeto (para los contadores de la interfaz). |
| `GET /contribuyentes/{id}/adjuntos/{aid}/archivo` | El archivo; en línea si es PDF o imagen, descarga con `?descargar=true`. |
| `PATCH /contribuyentes/{id}/adjuntos/{aid}` | Cambia la categoría o la nota. |
| `DELETE /contribuyentes/{id}/adjuntos/{aid}` | Elimina el soporte y su archivo. |
| `GET /contribuyentes/{id}/periodos-fiscales/{pid}/soportes/zip` | Todos los soportes del año (y los generales) en un ZIP ordenado por carpetas, con un `indice.csv`. |

Reglas:

- El formato se decide por el **contenido** del archivo (firma real), no por
  la extensión ni por el `Content-Type` que declare el cliente. Se admiten
  PDF, PNG, JPG, WEBP, GIF, XLSX, DOCX, CSV y TXT; cualquier otro responde
  415. Un SVG o un HTML disfrazado de imagen se rechaza.
- Tamaño máximo por archivo: `TAMANO_MAXIMO_ADJUNTO_MB` (15 por defecto),
  413 si se supera.
- El mismo archivo (misma huella SHA-256) no se adjunta dos veces al mismo
  objeto (409); sí puede respaldar objetos distintos.
- Adjuntar y editar la nota se permiten aunque el año esté cerrado (los
  soportes llegan tarde); **eliminar** exige reabrirlo (409).
- El activo `INVENTARIO` que genera el cierre no admite adjuntos (409).
- Al eliminar un activo, un ingreso o un contribuyente se eliminan también
  sus soportes.
- Solo PDF e imágenes se sirven en línea; el resto siempre como descarga.
