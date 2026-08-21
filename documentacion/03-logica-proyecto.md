# 3. Lógica del proyecto

## Flujo general

El flujo de uso completo, con sus dos rutas según el tipo de contribuyente,
está documentado en detalle en [08. Diagrama de
flujo](08-diagrama-flujo.md). Este documento explica la lógica interna de
los procesos clave.

## Proceso 1 — Registro y clasificación del contribuyente

Todo usuario inicia registrando su `Contribuyente` con un `tipoContribuyente`
(`ASALARIADO`, `INDEPENDIENTE` o `MIXTO`). Este valor determina qué módulos
de la aplicación se habilitan:

- `ASALARIADO` → solo módulo de patrimonio general.
- `INDEPENDIENTE` o `MIXTO` → módulo de patrimonio general **+** módulo de
  inventario.

## Proceso 2 — Cálculo del patrimonio líquido

El patrimonio líquido se calcula como la suma de todos los `Activo`
asociados al contribuyente (cuentas, vehículos, inmuebles, inversiones), más
—si aplica— el valor del inventario vigente (ver Proceso 4). Este cálculo es
el mismo para ambos perfiles de usuario; la diferencia es si existen o no
activos de tipo inventario.

## Proceso 3 — Registro de movimientos de inventario (solo negocio)

Cada `Movimiento` (entrada o salida) se valida contra el `Producto` al que
pertenece y contra el `MetodoCosteo` configurado para ese producto:

1. Se valida que el producto exista y esté activo.
2. Se valida que el movimiento tenga un `DocumentoSoporte` asociado.
3. Se calcula `valorTotal` como un valor derivado: `cantidad × valorUnitario`
   (no se almacena de forma independiente, para evitar inconsistencias).
4. Se actualiza el `stockActual` del producto.

## Proceso 4 — Cálculo del costo de ventas

Según el `metodoCosteo` configurado en el producto:

- **PEPS (primero en entrar, primero en salir)**: las salidas se costean
  usando el valor de las entradas más antiguas disponibles en el momento de
  la salida.
- **Promedio ponderado**: cada entrada recalcula el costo promedio del
  producto (`costoPromedio = valorTotalInventario / cantidadTotal`); las
  salidas se costean a ese promedio vigente.

El resultado alimenta el saldo de inventario y el costo de ventas del
periodo fiscal.

## Proceso 5 — Cierre de periodo fiscal

Al cerrar un `PeriodoFiscal` (normalmente al 31 de diciembre):

1. Se consolidan todos los movimientos del periodo.
2. Se calcula el saldo final de inventario (valorizado según el método de
   costeo).
3. Ese saldo se refleja como un `Activo` de tipo `INVENTARIO` dentro del
   patrimonio del contribuyente.
4. El periodo cambia su estado de `ABIERTO` a `CERRADO` y ya no admite
   nuevos movimientos.

## Proceso 6 — Generación de reportes

A partir del cierre, la aplicación genera:

- Kardex por producto (histórico de movimientos y saldos).
- Saldo final de inventario valorizado.
- Resumen de patrimonio e ingresos del contribuyente.
- Insumos para el formato 2517 de conciliación fiscal (si aplica).

Estos reportes son la salida final del sistema y el soporte que el usuario
utiliza para su declaración de renta ante la DIAN.
