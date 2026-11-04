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
