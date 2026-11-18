# modulos/exogena/

Importación del archivo Excel de información exógena descargado de la
DIAN. Ver Proceso 4 en
[03. Lógica del proyecto](../../../documentacion/03-logica-proyecto.md) y
HU-05/HU-06.

- `modelos.py`: `ReporteExogena`, `RegistroExogena`, `TopeExogena`,
  `ConceptoDian` (catálogo de referencia).
- `servicios.py`: localización de la fila de encabezados por contenido
  (no por número de fila fijo), separación del bloque de Topes,
  extracción de código de concepto y de renglón(es) sugerido(s) por
  expresión regular, marcado de filas autoreportadas o reportadas por la
  propia DIAN.

Filas no numéricas se devuelven como errores con su número de fila; el resto se importa.
