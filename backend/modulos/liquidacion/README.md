# modulos/liquidacion/

Liquida el impuesto de renta y complementarios de una persona natural
residente y produce el borrador del formulario 210, renglón por renglón,
con la fórmula y la norma que respaldan cada cifra.

Es el módulo que convierte la aplicación de un conciliador de exógena en
una herramienta de liquidación: antes, el borrador solo sumaba la columna
«Uso declaración Sugerida» del archivo de la DIAN y el contador tenía que
liquidar aparte.

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `motor.py` | El cálculo. Funciones puras sobre `Decimal`, sin base de datos. Recibe los parámetros del año; no conoce ningún número del Estatuto. |
| `calculos_empresariales.py` | Depreciación (arts. 128-137), bancarización (art. 771-5), compensación de pérdidas (arts. 147 y 330) y comparación patrimonial (arts. 236-239). Puros, probables por separado contra su norma. |
| `plantillas.py` | Catálogo de deducciones frecuentes con su norma y su tope propio. |
| `../parametros/tablas_oficiales.py` | Los parámetros tributarios por año gravable, cada uno con su fuente legal. Un año nuevo se agrega aquí, sin tocar el motor. |
| `clasificador.py` | Sugiere la cédula de una fuente de ingreso. Sugiere, no decide. |
| `modelos.py` | La hoja de liquidación, las deducciones solicitadas y la clasificación por cédula. |
| `servicios.py` | Arma los insumos desde la base y llama al motor. Convierte `float` a `Decimal` en la frontera. |
| `router.py` | La API. |

## Por qué el motor no toca la base de datos

La aritmética tributaria tiene que poder verificarse con lápiz y papel.
`tests/test_liquidacion_motor.py` recalcula cada tramo de la tabla del
art. 241 con la fórmula impresa en el Estatuto y compara: 45 pruebas que
corren en menos de un segundo sin Postgres. Las pruebas de la API van
aparte, en `tests/test_liquidacion_api.py`.

## Por qué `Decimal` y no `float`

El resto de la aplicación guarda dinero en `float`. En software contable
eso es un defecto: el error de representación binaria se acumula y los
totales dejan de cuadrar al centavo. Este módulo usa `Decimal` de punta a
punta y `NUMERIC(18,2)` en la base; la conversión ocurre en `_dec()`, en
`servicios.py`, que pasa por `str` a propósito —`Decimal(0.1)` arrastra el
error del float, `Decimal(str(0.1))` no—. Migrar los módulos antiguos está
pendiente y toca las pruebas existentes.

## Lo que el módulo no hace, a propósito

- **No decide la cédula de un ingreso.** Una clasificación equivocada
  cambia el impuesto: en rentas de capital y no laborales se restan costos
  y gastos, en rentas de trabajo con vínculo laboral no, y la exención del
  25 % solo aplica a estas últimas. Lo que el contador no confirme queda
  fuera del cálculo y aparece como diagnóstico.
- **No liquida años sin parámetros cargados.** Lanza
  `AnioGravableNoSoportadoError` en vez de usar los de otro año: una cifra
  equivocada que parece correcta es peor que un error visible.
- **No pone los números de renglón del formulario 210.** Los fija la
  resolución de la DIAN que prescribe el formulario de cada año. Los
  códigos de este módulo son propios y hay que mapearlos antes de
  transcribir.
- **No presenta la declaración.** No existe API pública de la DIAN para
  eso; se presenta en MUISCA con firma electrónica.
- **No incorpora sola la renta por comparación patrimonial.** El art. 236
  admite prueba en contrario: la calcula, la reporta y solo la suma a la
  base si el contador marca que la acepta. Incorporarla de oficio
  inventaría un impuesto.
- **No descuenta las operaciones en efectivo sobre 100 UVT.** Las lista
  para que el contador las revise: la consecuencia depende de si el pago
  se canalizó, y eso el software no lo sabe.

## La parte empresarial

Para un contribuyente con negocio, el motor además:

- **Trae el costo de ventas del kardex.** Es la deducción más grande de un
  comerciante. Antes se calculaba en el cierre y no llegaba a la
  liquidación, así que se liquidaba impuesto sobre el ingreso bruto.
- **Deprecia los activos fijos** por línea recta, con la vida útil que
  registre el contador, recortada a la tasa máxima del art. 137 y avisando
  cuando recorta.
- **Aplica el art. 771-5**: el efectivo aceptado es el menor entre el 40 %
  de los pagos, 40.000 UVT y el 35 % de los costos y deducciones. Lo
  rechazado vuelve a la renta líquida como renglón propio, para que se vea
  cuánto costó pagar en efectivo.
- **Compensa pérdidas** solo contra rentas del mismo tipo (art. 330) y
  dentro de los doce periodos del art. 147, consumiendo primero las más
  antiguas.
- **Reporta la pérdida del ejercicio.** Cuando los costos de una subcédula
  superan sus ingresos, la renta líquida se trunca en cero pero el exceso
  se muestra y se avisa: de lo contrario el contador vería una deducción en
  el borrador que no se restó en ninguna parte.
- **Calcula el anticipo por los dos procedimientos** del art. 807 y avisa
  cuando el promedio habría salido más barato. Sin impuesto neto del año
  anterior registrado, no usa el promedio: daría la mitad del anticipo que
  corresponde.

## Flujo

1. El contador registra las fuentes de ingreso y los activos (módulo
   `contribuyentes`).
2. `GET …/ingresos` devuelve cada fuente con una cédula sugerida;
   `PUT …/ingresos` guarda la que el contador confirma.
3. `PATCH …/hoja` captura lo que no está en ningún otro lado: aportes
   obligatorios, dependientes, dividendos certificados, ganancias
   ocasionales, deudas, anticipo del año anterior.
4. `POST …/deducciones` registra cada deducción o renta exenta
   solicitada, marcando si está sujeta al límite del art. 336 num. 3.
5. `GET …` liquida y devuelve los renglones, los diagnósticos y las notas.
6. `GET …/exportar` genera el papel de trabajo en Excel o PDF, con la
   fórmula y la norma de cada renglón.

Todas las escrituras quedan auditadas (módulo `auditoria`), incluidas las
decisiones profesionales —qué cédula se asignó, qué deducción se
solicitó—, que son las que habría que poder reconstruir frente a una
revisión.

## Límite legal, no técnico

La responsabilidad de la declaración es del contribuyente y del contador
que la firma (art. 581 ET). Este módulo es una herramienta de apoyo: todas
sus salidas llevan esa advertencia y están diseñadas para ser revisadas,
no para ser aceptadas a ciegas.

## La cédula general como grilla y el borrador del 210

El formulario 210 pide la cédula general como una grilla de diecisiete filas por
cuatro columnas (rentas de trabajo, de trabajo sin vínculo laboral, de capital y
no laborales). `cedula_general.py` arma esa grilla y el motor emite un renglón
`CG-C<número>` por cada celda con valor, con su número de casilla.

Reglas tomadas del instructivo oficial del formulario (AG 2024), no del texto
del Estatuto:

| Regla | Dónde |
|---|---|
| El cupo del art. 336 num. 3 se reparte en cascada: trabajo → sin vínculo → capital → no laborales | `_repartir_en_cascada` |
| Ninguna columna resta más que su propia renta líquida | `_repartir_en_cascada` |
| La base del 40 % no descuenta las devoluciones de la casilla 75 | `depurar` |
| Las rentas exentas sin límite se suman encima del 40 % | `depurar` |
| La adición por dependientes (139) se topa en las casillas 42 + 57 | `depurar` |
| El 1 % de compras (28) no puede generar pérdida | `depurar` |
| La compensación de pérdidas va después del límite (87 → 89 → 90) | `motor.liquidar` |
| Los descuentos (125) se topan en el impuesto de renta (121), no en renta + ganancia ocasional | `motor.liquidar` |
| La casilla 140 se marca si los costos de la 45 superan el 60 % de la 43 | `motor.liquidar` |

Cada deducción guarda su columna (`subcedula`) y su fila (`fila_formulario`). Si
el contador no fija la columna, el motor la reparte entre las columnas con renta
líquida en el orden del formulario.

`GET …/formulario-210` devuelve el borrador en PDF, casilla por casilla
(`borrador_210.py`). No es el formulario oficial: el 210 solo se presenta en los
servicios en línea de la DIAN, y el documento va marcado como borrador en cada
página. Las casillas que el motor no calcula (94, 95, 104–106, 109, 110,
118–120, 122, 123, 128, 135) se imprimen como «no calculada», no en cero.

## Dividendos gravados, sanciones, escenarios y arrastre

- **Dividendos gravados (casilla 118).** A los de la 2a subcédula se les aplica
  la tarifa del art. 240 (general 35 %, configurable por certificado) y solo el
  remanente entra a la tabla del art. 241: casilla 111 = mayor(97, 98) + 103 +
  107 + 108 − 118. La renta presuntiva se compara solo contra la cédula general.
- **Sanción por extemporaneidad (casilla 135, `sanciones.py`).** Art. 641 con
  la sanción mínima del 639 y las reducciones del 640, a partir de la fecha de
  vencimiento y de presentación del periodo. No cubre la sanción posterior al
  emplazamiento (art. 642) ni los intereses de mora, que dependen de la tasa
  que certifica la Superfinanciera cada mes.
- **Escenarios (`GET …/escenarios`).** Vuelve a liquidar con una sola decisión
  cambiada: costos contra renta exenta del 25 % en honorarios, método del
  anticipo, cupo sin usar del art. 336. Son cálculos, no recomendaciones.
- **Imputación de deducciones (`PATCH …/deducciones/{id}/imputacion`).** Fija
  la columna y la fila del formulario de cada deducción.
- **Arrastre.** Al copiar la hoja del año anterior, las pérdidas del ejercicio
  quedan registradas como compensables.
- **Numeración.** La Resolución DIAN 000044 de 2024 prescribe el formulario
  «para el año gravable 2023 y siguientes» (compilada en la Resolución 227 de
  2025): la numeración vale para 2023 a 2025. Un año posterior se marca como
  no verificado.

El costeo del inventario (PEPS y promedio) hace su aritmética en `Decimal`. Los
campos de dinero de los módulos anteriores siguen guardados como `float` en la
base de datos; migrarlos es un cambio de esquema pendiente.
