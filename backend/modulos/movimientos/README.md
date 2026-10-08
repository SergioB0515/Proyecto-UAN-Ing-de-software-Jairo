# modulos/movimientos/

Registro de `Movimiento` (entradas/salidas), `Proveedor` y
`DocumentoSoporte`; kardex y costo de ventas (PEPS / promedio ponderado).
Ver Procesos 8 y 9 en
[03. Lógica del proyecto](../../../documentacion/03-logica-proyecto.md) y
HU-12 a HU-14.

- `modelos.py`: tablas `Proveedor`, `DocumentoSoporte`, `Movimiento` y los
  resultados calculados `Kardex` y `CostoVentasPeriodo`.
- `costeo.py`: motor de costeo como funciones puras (sin base de datos),
  probado en `tests/test_costeo.py`.
- `servicios.py`: validaciones del Proceso 8 y cálculo del costo de ventas.

Reglas:

- Todo movimiento exige un `DocumentoSoporte` del mismo contribuyente; un
  documento puede respaldar varios movimientos (una factura con varias
  líneas).
- La fecha del movimiento debe caer en el año gravable de su periodo, y el
  periodo debe estar `ABIERTO`.
- El proveedor es opcional y solo aplica a entradas.
- `valor_unitario` es el costo de compra en una ENTRADA y el precio de venta
  en una SALIDA; `valor_total` es derivado y no se almacena.
- Una salida se rechaza (409) si deja el stock en negativo en cualquier
  punto de la línea de tiempo, aunque se registre con fecha anterior.
- El costo de cada salida no se guarda: el kardex se recalcula
  reproduciendo los movimientos en orden cronológico, así una compra
  registrada tarde corrige el costo de las ventas posteriores.
