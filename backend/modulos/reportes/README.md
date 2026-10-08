# modulos/reportes/

Cierre de `PeriodoFiscal`, resumen por contribuyente y reportes
exportables en Excel (`openpyxl`) y PDF (`reportlab`). Ver Procesos 10 y 11
en [03. Lógica del proyecto](../../../documentacion/03-logica-proyecto.md)
y HU-15 a HU-17.

- `modelos.py`: tabla `CierrePeriodo` (qué hizo cada cierre, para poder
  deshacerlo) y el resultado calculado `ResumenContribuyente`.
- `servicios.py`: cerrar/reabrir, resumen y armado de cada reporte como
  una lista de secciones.
- `exportacion.py`: dibuja secciones en Excel o PDF; no conoce el negocio.

Reglas del cierre:

- Los periodos se cierran en orden de año y solo se reabre el último
  cerrado: el saldo inicial de un año depende del cierre del anterior.
- Si el contribuyente maneja inventario, el saldo final valorizado se
  registra como `Activo` de tipo `INVENTARIO` (aunque valga 0). El
  patrimonio cuenta solo el del último cierre.
- Un periodo cerrado no admite movimientos ni importaciones de exógena.
  Reabrir borra el `Activo` creado y vuelve el periodo a `ABIERTO`.
