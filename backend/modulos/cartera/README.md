# modulos/cartera/

Vista de solo lectura que agrega, para todos los contribuyentes del
contador autenticado, su estado de obligación de declarar (módulo
`parametros`) y su número de alertas de conciliación (`NO_DECLARADO`, del
módulo `conciliacion`). No tiene modelo de datos propio ni endpoints de
escritura. Ver Proceso 11 en
[03. Lógica del proyecto](../../../documentacion/03-logica-proyecto.md) y
HU-18.

`GET /cartera` evalúa el periodo más reciente de cada contribuyente, o el
de `anio_gravable` si se indica. Por defecto ordena por alertas (más
urgentes primero, y a igual número, los obligados a declarar); con
`orden=nombre`, alfabéticamente. Los contribuyentes que no se pueden
evaluar (sin periodo, sin exógena o sin umbral) van al final, con el motivo
en `avisos`.
