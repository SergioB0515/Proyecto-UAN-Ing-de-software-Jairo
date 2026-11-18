# modulos/cartera/

Vista de solo lectura de todos los contribuyentes del contador: obligación de
declarar, vencimiento, alertas `NO_DECLARADO` y etapa de la declaración. HU-18, HU-25, HU-27.

`GET /cartera?anio_gravable=&orden=alertas|nombre|vencimiento`. Por defecto el
periodo más reciente. Los no evaluables (sin periodo, exógena o umbral) van al
final con el motivo en `avisos`. `GET /cartera/exportar?formato=xlsx|pdf`.
