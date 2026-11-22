# 12. Plan de trabajo inmediato

> Corte al **22 de noviembre de 2026**, con la entrega ya presentada y
> revisada.

Este documento no reemplaza al [11](11-roadmap-tecnico-y-monetizacion.md).
Ese dice *hacia dónde* y *por qué*: mercado, precios, tesis, módulos que
faltan. Este dice **qué se construye ahora y en qué orden**, y solo incluye
trabajo que se puede empezar hoy sin depender de nadie más.

---

## 0. Qué cambió desde el documento 11

El 11 tiene corte al 3 de noviembre y quedó desactualizado en cuatro puntos:

| Dice el 11 | Hoy |
|---|---|
| 325 pruebas | 579 |
| «Portal del contribuyente», prioridad media, 10–15 días | Construido y desplegado |
| 61 campos de dinero en `float` | 56, y 162 usos de `Decimal` en los módulos nuevos |
| 9 ítems de deuda técnica, ninguno hecho | Sigue igual: ninguno hecho |

Y apareció algo que el 11 no contemplaba, que es el punto de partida de este
plan.

---

## 1. El hilo que une los dos defectos que llegaron a producción

Ninguno de los dos fue un error de lógica tributaria. Los dos fueron
**actualizaciones de esquema**:

1. `create_all` no agrega columnas a una tabla que ya existe. El despliegue
   con datos arrancó y falló al primer `SELECT`.
2. `create_all` tampoco agrega valores a un tipo ENUM que ya existe. Marcar
   «no lo tengo» o subir un soporte devolvía 500.

Lo importante no es que hubiera dos defectos. Es **por qué ninguna prueba los
vio**, y la respuesta no es la que parece.

El CI ya corre contra Postgres 16, no contra SQLite. El problema es que
levanta un contenedor de Postgres **nuevo en cada corrida**: la base nace
vacía y el esquema se crea completo de una vez. En una base recién creada
estos dos defectos **no existen**. Solo existen en una base que lleva tiempo
viva, y de esas hay exactamente una: la de producción.

Dicho de otro modo: el proyecto prueba muy bien una **instalación nueva** y no
prueba en absoluto una **actualización**. Las 579 pruebas no se equivocaron;
están contestando otra pregunta.

Esto importa ahora y no después porque el siguiente trabajo de la lista
—migrar 56 columnas de dinero— es la actualización de esquema más grande que
va a tener este proyecto, y hoy no hay nada con qué verificarla.

---

## 2. Bloque 1 — Que una actualización se pueda probar

**Esfuerzo: 1,5–2,5 días. Riesgo: bajo. Va primero.**

### 1.1 Prueba de actualización en el CI (medio día)

Un segundo job que, en vez de partir de una base vacía:

1. Hace *checkout* del último tag publicado y crea el esquema con **ese**
   código.
2. Siembra unas filas, para que la base tenga datos que no se puedan perder.
3. Vuelve al commit actual y corre `crear_tablas()` encima.
4. Corre la suite completa contra esa base.

Eso atrapa los dos defectos de arriba, y de paso cualquier migración futura
que se olvide. Es la prueba que faltaba, no una más.

Requiere empezar a poner tags de versión, que hoy no hay. Es parte del
trabajo.

### 1.2 Alembic (1–2 días)

No está instalado; las migraciones son `ALTER TABLE` a mano dentro de
`database.py` (`_agregar_columnas_si_faltan`, `_sincronizar_enums`,
`_migrar_periodo_en_activos_y_fuentes`). Funcionan, pero cada una hubo que
escribirla después de que el defecto apareciera en producción.

**El orden 1.1 → 1.2 no es negociable.** Alembic sin la prueba de
actualización es otra forma de escribir migraciones que nadie verifica. Con
la prueba primero, adoptarlo se puede comprobar en vez de suponer: los
helpers actuales se van convirtiendo en revisiones de Alembic una por una, y
la prueba dice si cada conversión preservó el comportamiento.

---

## 3. Bloque 2 — El dinero en `Decimal`

**Esfuerzo: 3–5 días. Riesgo: alto. Es el defecto más serio que queda.**

Quedan 56 campos monetarios en `float`. Los módulos nuevos ya usan
`Decimal`/`NUMERIC(18,2)`: 162 usos. Eso significa que hoy el proyecto tiene
**dos convenciones a la vez**, y el lugar donde se pierden los centavos es
justo la frontera, cuando un valor pasa de un módulo `float` a un módulo
`Decimal`.

Que esté dividido lo empeora, pero también lo hace más fácil de terminar: la
mitad nueva ya demuestra que el patrón funciona en este código, con estas
pruebas y contra este motor.

Por qué va después del bloque 1 y no antes: migrar 56 columnas **es** una
actualización de esquema. Hacerlo sin la prueba de actualización es repetir el
error de los dos defectos anteriores, con cincuenta y seis oportunidades de
equivocarse en vez de tres.

Lo que lo hace abordable ahora y no en noviembre:

- 579 pruebas en verde como red, contra Postgres.
- El trabajo es mecánico, campo por campo, y se puede partir por módulo.
- Postgres se reproduce en local, así que un descuadre se ve antes de subirlo.

---

## 4. Bloque 3 — Cerrar lo que quedó a medias

**Esfuerzo: 1,5–2 días. Riesgo: bajo.** Se puede intercalar con los otros.

- **Historias de usuario del portal.** El documento 06 va de HU-01 a HU-27 y
  no tiene ninguna del portal: ni el enlace de carga, ni la autorización de
  tratamiento, ni los cuatro estados, ni los adicionales, ni la verificación
  de identidad. La función está construida y documentada en el README del
  módulo, pero no como historia con criterios de aceptación, que es el
  formato que pide el curso. Van de HU-28 en adelante.
- **Actualizar el documento 11** con la tabla de la sección 0.
- **Consolidar las tablas laterales de liquidación**
  (`clasificaciones_ingreso`, `datos_depreciacion`) como columnas de
  `fuentes_ingreso` y `activos`. Era el ítem 3 del 11, y después del bloque 1
  cuesta menos, porque es exactamente el tipo de cambio que Alembic hace sin
  drama.

---

## 5. Bloque 4 — La primera función nueva: simulador de planeación

**Esfuerzo: 5–7 días. Riesgo: bajo.**

> «¿Cuánto me baja el impuesto si aporto 20 millones a un AFC?»

De los tres módulos que el 11 pone como siguientes, este es el que hay que
construir ahora, y no por tamaño:

- **No hay ley nueva que codificar.** Es recalcular la liquidación con
  insumos alterados. Todo el motor ya está hecho, parametrizado por año y
  probado. El trabajo es la interfaz y el manejo de escenarios.
- **Produce un número comparable**, que es lo que convierte esto en algo
  medible y no solo en una pantalla más. Las dos ideas de tesis del
  documento 11 que tienen resultado graficable se apoyan en eso.
- **Es lo más convincente que se puede mostrar en dos minutos.** Un contador
  entiende de inmediato para qué sirve.

**Retención en la fuente** (8–12 días) es el módulo correcto el día que haya
un contador usando esto todos los meses, porque convierte el producto de
estacional a recurrente. Hoy no lo hay, y son ocho a doce días de codificar
procedimientos 1 y 2 sin aprender nada nuevo de arquitectura. Cuando aparezca
ese contador, ese módulo pasa al primer lugar y este documento se reescribe.

**Exógena como reportante** (15–20 días) queda esperando por lo mismo, y
porque es el doble de trabajo.

---

## 6. En paralelo, y no cuesta días de código

La contadora que revisó la herramienta no dio ideas nuevas. Eso es una señal
débil, no una buena noticia: alguien a quien le muestran una demostración
tiende a decir que se ve bien, porque no tiene cómo decir otra cosa en ese
momento.

La pregunta que sí sirve no es «¿qué le falta?», es:

> «¿Me prestas dos declaraciones que ya hayas presentado, anonimizadas, para
> comparar cifra contra cifra?»

Eso convierte una opinión en un dato. Si las cifras cuadran, es el resultado
más fuerte que este proyecto puede mostrar y la base de la tesis más
defendible del documento 11. Si no cuadran, hay que saberlo ahora, que es
cuando arreglarlo todavía es barato.

Es el ítem 1 de «lo primero que haría» del documento 11, sigue sin hacerse, y
es lo único de esta lista que depende de otra persona. Por eso se pide ya, y
mientras llega se trabaja en el bloque 1.

---

## 7. Lo que NO está en este plan

Para que se entienda que es una omisión decidida y no un olvido:

- **Capa de organización (firma → contadores → roles).** Es el techo
  comercial, pero es techo de venta y aquí no hay nada que vender todavía.
- **Respaldos, cifrado en reposo, segundo factor, límite de peticiones.**
  Obligatorios antes del primer cliente real con datos reales. No antes.
- **Observabilidad.** Mismo criterio: duele cuando hay usuarios que no eres
  tú.
- **Catálogo de conceptos de la DIAN y mapeo al formulario 210.** Mejoran la
  fiabilidad, no desbloquean nada.
- **IVA, ICA, facturación electrónica, app móvil.** Siguen descartados por
  las razones del documento 11, que no han cambiado.

---

## 8. Resumen

| Orden | Trabajo | Esfuerzo | Riesgo |
|---|---|---|---|
| 1 | Prueba de actualización en el CI, con tags de versión | 0,5 d | Bajo |
| 2 | Alembic, convirtiendo los helpers actuales en revisiones | 1–2 d | Bajo |
| 3 | 56 campos de dinero a `Decimal`/`NUMERIC(18,2)` | 3–5 d | **Alto** |
| 4 | Historias de usuario del portal (HU-28+) y actualizar el 11 | 1 d | Bajo |
| 5 | Consolidar las tablas laterales de liquidación | 1 d | Bajo |
| 6 | Simulador de planeación tributaria | 5–7 d | Bajo |

Entre dos y tres semanas de trabajo de una persona. En paralelo y desde el
primer día: pedir las dos declaraciones reales.

El criterio detrás del orden es uno solo: **primero lo que hace verificable
lo que viene después.** Los bloques 1 y 2 no agregan una sola pantalla y son
lo que permite que el bloque 4 no se construya encima de cimientos que nadie
ha probado.
