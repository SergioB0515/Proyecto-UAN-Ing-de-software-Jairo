# 3. Lógica del proyecto

## Flujo general

El flujo de uso completo está documentado en detalle en [08. Diagrama de
flujo](08-diagrama-flujo.md). Este documento explica la lógica interna de
los once procesos clave, en el orden en que normalmente ocurren para un
contador que atiende a un contribuyente.

## Proceso 1 — Autenticación del contador

El contador se registra e inicia sesión con usuario y contraseña. El
backend valida la contraseña (hash con argon2) y emite un token JWT que la
SPA adjunta en cada petición posterior. El contribuyente **no** tiene
inicio de sesión propio en este alcance: todos los datos los carga el
contador en su nombre.

## Proceso 2 — Registro y clasificación del contribuyente

El contador registra un `Contribuyente` asociado a su propia cuenta
(`contribuyente.contador_id`), con un `tipoContribuyente`
(`ASALARIADO`, `INDEPENDIENTE` o `MIXTO`). Este valor determina qué
módulos se habilitan para ese contribuyente:

- `ASALARIADO` → solo módulo de patrimonio general.
- `INDEPENDIENTE` o `MIXTO` → módulo de patrimonio general **+** módulo de
  inventario.

## Proceso 3 — Cálculo del patrimonio líquido

El patrimonio líquido de un año gravable se calcula como la suma de los
`Activo` del contribuyente registrados en ese `PeriodoFiscal` (cuentas,
vehículos, inmuebles, inversiones), más —si aplica— el inventario final que
registra el cierre de ese mismo periodo (ver Proceso 10). Cada `Activo` y
cada `FuenteIngreso` pertenece a un periodo, porque el patrimonio se
declara al 31 de diciembre de cada año y los ingresos son los del año. Este
cálculo es el mismo para ambos perfiles de contribuyente.

Al registrar un `Activo` o una `FuenteIngreso`, el contador puede
opcionalmente indicar un **vínculo DIAN**: un código de concepto (ej.
`1032`) o una palabra clave del detalle (ej. `"avalúo catastral"`). Ese
vínculo es lo que permite el cruce automático en el Proceso 6; si no se
indica, la app puede sugerir uno a partir del catálogo del Proceso 4.

## Proceso 4 — Importación de información exógena

El contador descarga previamente, desde el portal transaccional de la
DIAN, el archivo Excel de información exógena del contribuyente para el
año gravable correspondiente (este paso ocurre fuera de la aplicación; la
DIAN no ofrece una API pública para consultarlo). Dentro de la aplicación:

1. El contador sube el archivo Excel para un `Contribuyente` y
   `PeriodoFiscal` específicos.
2. El servicio de importación (con `pandas`) localiza la fila de
   encabezados reales (la que contiene literalmente `NIT` /
   `Nombre...`) en vez de asumir un número de fila fijo — el bloque de
   metadatos que la precede (título, advertencias legales, identificación
   del consultante) varía de longitud entre archivos.
3. Inmediatamente debajo de los encabezados, el archivo trae un bloque de
   **"Topes"** (Ingresos, Patrimonio, Consumo TC, Movimiento, Compras): son
   subtotales que la propia DIAN ya calculó, no registros de un tercero. Se
   reconocen porque la columna de NIT reportante viene vacía. Se guardan
   aparte (no como `RegistroExogena`) y se usan en el Proceso 5.
4. Cada fila restante con NIT reportante se guarda como un
   `RegistroExogena`, agrupado bajo un `ReporteExogena` (uno por
   contribuyente y periodo). De cada fila se extrae, con expresiones
   regulares sobre la columna `Detalle`:
   - el **código de concepto DIAN**, si está presente entre paréntesis
     (`(Concepto: 1032)`) — no todas las filas lo traen (las filas de
     agregados propios o de la DIAN, ver punto 5, normalmente no);
   - el o los **renglones sugeridos** de la columna `Uso declaración
     Sugerida` (patrón `R\d+`, ej. `R29`, `R112`), usados en el Proceso 7.
5. Cada fila queda marcada si es **autoreportada** (el NIT que reporta es
   el mismo del consultante — son datos de la propia declaración del año
   anterior, no un cruce con un tercero) o si el reportante es la **propia
   DIAN** (agregados como el total de compras en factura electrónica). Esta
   marca es la que el Proceso 6 usa para no tratarlas como una fuente de
   riesgo si no coinciden con algo declarado.
6. Filas que no se puedan interpretar (formato inesperado, valor no
   numérico en una fila que no es de tope) se reportan al contador con el
   número de fila y el motivo, en vez de descartarse en silencio.

> El bloque de "Topes" **no se usa para validar la suma de los
> `RegistroExogena` importados**. Se verificó contra un archivo real que el
> tope de Patrimonio no es una suma simple de las filas relacionadas: el
> propio archivo indica que toma "el mayor valor entre la suma de variables
> del año gravable y el patrimonio bruto declarado el año anterior", una
> fórmula que no se puede reconstruir de forma confiable solo con este
> archivo. Los Topes se tratan como referencia informativa (Proceso 5) y no
> como una validación cruzada del parser.

### Catálogo de conceptos DIAN

Para reducir cuánto tiene que saber el contador de memoria, el módulo
`exogena` mantiene una tabla de referencia (`ConceptoDian`: código,
descripción, categoría) con los códigos que se identifiquen en uso. Al
registrar un `Activo` o `FuenteIngreso`, la app puede sugerir un vínculo a
partir de esta tabla en vez de exigir que el contador teclee el código de
memoria. Es una tabla que crece con el uso real de la aplicación, no un
listado cerrado que haya que completar de una vez.

## Proceso 5 — Verificación de obligación de declarar

Con los Topes ya extraídos (Proceso 4), el sistema los compara contra una
tabla de umbrales vigente para el año gravable (`UmbralDeclaracion`: valor
UVT y los cinco topes en pesos), y determina si el contribuyente está
obligado a declarar según el criterio de la DIAN: basta con **superar uno**
de los cinco para quedar obligado.

| Tope del archivo | Criterio legal |
|---|---|
| Ingresos | Ingresos brutos ≥ 1.400 UVT |
| Patrimonio | Patrimonio bruto ≥ 4.500 UVT |
| Consumo TC | Consumos con tarjeta de crédito ≥ 1.400 UVT |
| Compras | Compras y consumos ≥ 1.400 UVT |
| Movimiento | Consignaciones, depósitos o inversiones ≥ 1.400 UVT |

La tabla `UmbralDeclaracion` es **configurable por año gravable**, no un
valor fijo en el código: la UVT y los topes cambian cada año por resolución
de la DIAN.

Este resultado es una **señal de apoyo, no un veredicto legal completo**:
existe un sexto criterio (haber sido responsable de IVA durante el año) que
no aparece en el archivo de exógena y que la aplicación no puede evaluar —
el contador debe seguirlo verificando por su cuenta. La interfaz debe dejar
esto explícito cada vez que se muestre el resultado.

## Proceso 6 — Conciliación de información exógena

Con el `ReporteExogena` ya importado, el motor de conciliación cruza cada
`Activo` y `FuenteIngreso` declarado contra los `RegistroExogena`, usando
el vínculo DIAN de cada uno (código de concepto o palabra clave, Proceso
3). Por cada ítem declarado, el resultado queda clasificado en uno de estos
estados:

- **COINCIDE**: se encontró un `RegistroExogena` vinculado y el valor
  coincide dentro de una tolerancia (para diferencias de redondeo).
- **DISCREPANCIA**: se encontró un `RegistroExogena` vinculado pero el
  valor difiere más allá de la tolerancia.
- **NO_REPORTADO_POR_TERCERO**: el contador lo registró, pero no se
  encontró ningún `RegistroExogena` vinculado — señal de menor riesgo
  (puede deberse a que el tercero aún no reportó, o a una fuente de ingreso
  que no genera reporte exógeno).

Adicionalmente, todo `RegistroExogena` que **no** quedó vinculado a ningún
ítem declarado se reporta como:

- **NO_DECLARADO**: apareció en la exógena pero no hay nada registrado que
  lo explique — la señal de mayor riesgo.

Quedan **excluidas del cruce** las filas autoreportadas o reportadas por la
propia DIAN (Proceso 4, punto 5) — no son un cruce real con un tercero — y
las filas cuyo detalle indica una **retención** (ej. "Retención practicada
en Notaría"): la DIAN reutiliza el mismo código de concepto para el valor
de un ingreso y para la retención asociada a ese ingreso (ambos bajo el
código `1032` en el caso de notarías), y agruparlas junto al ingreso
mezclaría dos magnitudes distintas.

El resultado de la conciliación no modifica los datos ya registrados; es un
reporte de apoyo para que el contador decida si corrige la declaración,
contacta al tercero reportante, o documenta la diferencia.

## Proceso 7 — Borrador de renglones sugeridos

A partir de los renglones extraídos en el Proceso 4 (columna `Uso
declaración Sugerida`), el sistema agrupa los valores de los
`RegistroExogena` por renglón (`R29`, `R112`, `R131`, `R132`...) y presenta
un borrador con el total sugerido por renglón. No reemplaza el
diligenciamiento del formulario oficial ni el criterio del contador —es un
punto de partida ya sumado, en vez de que el contador arme esa suma a mano
concepto por concepto.

## Proceso 8 — Registro de movimientos de inventario (solo negocio)

Cada `Movimiento` (entrada o salida) se valida contra el `Producto` al que
pertenece y contra el `MetodoCosteo` configurado para ese producto:

1. Se valida que el producto exista y esté activo.
2. Se valida que el movimiento tenga un `DocumentoSoporte` asociado.
3. Se calcula `valorTotal` como un valor derivado: `cantidad × valorUnitario`
   (no se almacena de forma independiente, para evitar inconsistencias).
4. Se actualiza el `stockActual` del producto.

## Proceso 9 — Cálculo del costo de ventas

Según el `metodoCosteo` configurado en el producto:

- **PEPS (primero en entrar, primero en salir)**: las salidas se costean
  usando el valor de las entradas más antiguas disponibles en el momento de
  la salida.
- **Promedio ponderado**: cada entrada recalcula el costo promedio del
  producto (`costoPromedio = valorTotalInventario / cantidadTotal`); las
  salidas se costean a ese promedio vigente.

## Proceso 10 — Cierre de periodo fiscal

Al cerrar un `PeriodoFiscal` (normalmente al 31 de diciembre):

1. Se consolidan todos los movimientos del periodo.
2. Se calcula el saldo final de inventario (valorizado según el método de
   costeo).
3. Ese saldo se refleja como un `Activo` de tipo `INVENTARIO` dentro del
   patrimonio del contribuyente.
4. El periodo cambia su estado de `ABIERTO` a `CERRADO` y ya no admite
   nuevos movimientos ni nuevas importaciones de exógena para ese año.

## Proceso 11 — Generación de reportes y panel de cartera

A partir del cierre, la aplicación genera, por contribuyente:

- Estado de obligación de declarar (Proceso 5).
- Reporte de conciliación (Proceso 6).
- Borrador de renglones sugeridos (Proceso 7).
- Kardex por producto (histórico de movimientos y saldos), si aplica.
- Saldo final de inventario valorizado, si aplica.
- Resumen de patrimonio e ingresos.

Además, el contador tiene un **panel de cartera**: una vista que agrega,
para todos sus contribuyentes a la vez, si están obligados a declarar y
cuántas alertas de conciliación (`NO_DECLARADO`) tiene cada uno — para que
pueda priorizar a quién atender primero sin entrar contribuyente por
contribuyente.

Estos reportes son la salida final del sistema y el soporte que el contador
entrega a cada contribuyente para su declaración de renta ante la DIAN.
