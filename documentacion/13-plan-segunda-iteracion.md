# 13. Plan de trabajo — segunda iteración

> Corte al **22 de noviembre de 2026**, con el documento
> [12](12-plan-inmediato.md) cerrado.

El documento 11 sigue siendo el de mercado, monetización y tesis. El 12
cubrió los seis puntos de la primera iteración. Este dice qué sigue y en qué
orden, con el mismo criterio: solo trabajo que se puede empezar hoy.

---

## 0. De dónde parte

Los seis puntos del documento 12, cerrados:

| | Punto | Resultado |
|---|---|---|
| 1 | Prueba de actualización en el CI | Hecho |
| 2 | Alembic con comprobación de deriva | Hecho |
| 3 | 56 campos de dinero a `Decimal` | Hecho |
| 4 | Historias del portal (HU-28 a HU-36) | Hecho |
| 5 | Consolidar las tablas laterales | **Descartado**: estaba mal planteado |
| 6 | Simulador de planeación | Hecho, y mucho más pequeño de lo estimado |

Estado medible hoy:

| Métrica | Valor |
|---|---|
| Pruebas del backend | 588, contra PostgreSQL |
| Pruebas del frontend | **0** |
| Líneas de frontend | 9.309 |
| Historias de usuario | 36 (HU-01 a HU-36) |
| Incrementos con evidencia en el documento 10 | 8 de 9 |
| Campos de dinero en `float` | 0 |
| Migraciones | Versionadas con Alembic, con prueba de actualización |

---

## 1. La asimetría que quedó

El documento 12 arrancó de una observación: el proyecto probaba muy bien una
instalación nueva y no probaba en absoluto una actualización. Eso quedó
resuelto.

Queda la misma forma de problema del otro lado. El backend tiene 588 pruebas,
corre contra PostgreSQL en integración continua, migra con revisiones
versionadas y verifica que el esquema desplegado sobreviva a una
actualización. El frontend tiene **9.309 líneas y ninguna prueba**.

No es una preocupación teórica. En esta misma iteración aparecieron tres
defectos reales en el frontend y los tres salieron **leyendo el código**, no
ejecutándolo: `PatrimonioView` sumaba con `+` tres campos que pasaron a
llegar como cadena, y habría mostrado «04000000.001500000.00» en lugar del
total. Se encontraron porque alguien fue a buscarlos a mano después de un
cambio de tipos. La próxima vez puede que nadie vaya a buscar.

El frontend además dejó de ser una capa de presentación: la regla de plegado
de la liquidación decide qué se muestra según el tipo de contribuyente y los
datos capturados, y el portal del contribuyente tiene lógica de estados y de
validación. Eso es comportamiento, y el comportamiento sin prueba se rompe en
silencio.

---

## 2. Bloque 1 — Que el frontend también se pueda verificar

**Esfuerzo: 1–2 días. Riesgo: bajo. Va primero.**

Vitest y Vue Test Utils, que es lo que usa el ecosistema de Vite sin
configuración adicional, y un trabajo más en el CI junto a los tres que ya
hay.

No se trata de cubrir 9.309 líneas. Se trata de empezar por lo que ya mordió
y por lo que tiene lógica de verdad:

- **Aritmética sobre dinero.** El backend manda los importes como cadena
  porque son `NUMERIC`. Toda suma del frontend tiene que convertir. Es el
  defecto que ya apareció tres veces en el mismo archivo.
- **La regla de plegado de la liquidación.** Decide qué secciones se abren
  según el tipo de contribuyente y según si hay datos capturados, y ya tuvo
  un error: contaba como dato capturado un entero con valor por omisión.
- **Los cuatro estados del portal** y qué cuenta como documento resuelto.

El criterio es el mismo del bloque 1 del documento 12: primero lo que hace
verificable lo que viene después.

---

## 3. Bloque 2 — Cerrar lo que el curso pide

**Esfuerzo: 1 día. Riesgo: bajo.**

- **Evidencias del incremento 9.** El documento 10 llega hasta el incremento
  8. Las nueve historias del portal (HU-28 a HU-36) y el simulador de aporte
  no tienen captura. El formato del curso es una evidencia por historia.
- **Datos de demostración para dos funciones que existen y no se ven.**
  `clasificaciones_ingreso` y `datos_depreciacion` tienen **cero filas** en
  la semilla. La clasificación manual de una fuente de ingreso y la
  depreciación de un activo están construidas y probadas, pero no se pueden
  mostrar en una sustentación ni se ven en la aplicación desplegada. Es el
  tipo de hueco que solo se nota cuando alguien pregunta en vivo.

---

## 4. Bloque 3 — Tres cosas conocidas y sin arreglar

**Esfuerzo: 1 día entre las tres. Riesgo: bajo.**

Aparecieron durante la primera iteración, quedaron documentadas y no se
corrigieron, para no mezclarlas con el trabajo que estaba en curso.

**`Liquidacion.valor()` devuelve cero cuando el código de renglón no
existe.** Un código mal escrito no produce error: apaga el cálculo en
silencio. Ya costó una vez —el techo del 30 % de los arts. 126-1 y 126-4
quedó inactivo y solo se notó porque las cifras de la demostración no
cuadraban—. Las opciones son que falle al no encontrar el código, o un modo
estricto para los llamados que no toleran un cero. Lo que no sirve es dejarlo
como está y confiar en que el siguiente también se note.

**El portal y el simulador leen distinto el mismo límite.** El portal valida
los aportes a AFC solo contra el tope en UVT; el simulador aplica además el
30 % del ingreso. El portal no puede aplicarlo en ese momento porque no
conoce el ingreso del periodo, lo cual es una razón válida, pero el resultado
es que el mismo artículo tiene dos lecturas en el mismo proyecto. Hay que
elegir una: que el portal avise del segundo techo sin calcularlo, o que lo
calcule cuando el periodo ya tenga ingresos registrados.

**Las tablas laterales repiten `periodo_fiscal_id`.** `clasificaciones_ingreso`
y `datos_depreciacion` guardan un periodo que ya está en `fuentes_ingreso` y
en `activos`. Es una desnormalización para consultar sin join, y dos copias
del mismo dato pueden divergir. El arreglo es quitar la columna y consultar
con join.

---

## 5. Bloque 4 — La decisión que decide el resto

Hasta aquí todo lo pendiente era claro: faltaba y había que hacerlo. De este
punto en adelante los dos caminos del proyecto piden cosas distintas, y
conviene decidir antes de gastar una semana.

**Si el proyecto sigue como producto**, lo siguiente es **retención en la
fuente** (8–12 días, documento 11). Es mensual, no anual, y es lo que
convierte la herramienta de estacional en recurrente. Es también el trabajo
más lento de los que quedan: codificar los procedimientos 1 y 2 sin aprender
nada nuevo de arquitectura.

**Si el proyecto sigue como tesis**, lo siguiente es la **validación
empírica**: liquidar con la herramienta dos o tres declaraciones reales ya
presentadas, anonimizadas, y comparar cifra contra cifra contra el trabajo
manual del contador.

### Lo que haría primero, en cualquiera de los dos casos

La validación empírica, y antes que el bloque 4 completo.

No es código, no compromete el camino que se elija y alimenta los dos. Si las
cifras cuadran, es el resultado más fuerte que este proyecto puede mostrar, y
es la base de la tesis más defendible del documento 11. Si no cuadran, hay
que saberlo ahora, que es cuando corregirlo todavía es barato.

Sigue sin hacerse desde que se escribió el documento 11, y es lo único de
toda esta lista que depende de otra persona, así que es lo que más tarda en
empezar. La pregunta a la contadora no es «¿qué le falta?» —a eso, viendo una
demostración, se responde que se ve bien— sino «¿me prestas dos declaraciones
que ya hayas presentado?».

---

## 6. Lo que no está en este plan

Omisiones decididas, con el criterio de cuándo entrarían:

- **Capa de organización: firma, contadores, roles.** Es el techo comercial,
  pero es techo de venta y todavía no hay nada que vender.
- **Respaldos, retención y cifrado en reposo.** Obligatorios antes del primer
  cliente real con datos reales. El art. 632 ET obliga a conservar soportes
  cinco años.
- **Observabilidad y límite de peticiones.** Duelen cuando hay usuarios que
  no son uno mismo.
- **Catálogo de conceptos de la DIAN por resolución anual.** Hoy la
  clasificación se sugiere por palabras del concepto; por código sería más
  fiable. Mejora la calidad, no desbloquea nada. El `clasificador.py` lo
  tiene anotado.
- **Mapeo renglón → formulario 210 oficial.** Mismo criterio.
- **Exógena como reportante, IVA, ICA, facturación electrónica.** Siguen con
  las razones del documento 11, que no han cambiado.

---

## 7. Resumen

| Orden | Trabajo | Esfuerzo | Riesgo |
|---|---|---|---|
| 0 | Pedir dos declaraciones reales para la validación empírica | — | — |
| 1 | Vitest y las primeras pruebas del frontend, en el CI | 1–2 d | Bajo |
| 2 | Evidencias del incremento 9 y datos demo de clasificación y depreciación | 1 d | Bajo |
| 3 | Los tres defectos conocidos del bloque 3 | 1 d | Bajo |
| 4 | Retención en la fuente, **o** la validación empírica a fondo | 8–12 d / — | Medio |

Los tres primeros son menos de una semana y no comprometen ninguna decisión.
El cuarto depende de la respuesta a la pregunta del bloque 4, y el punto 0 no
cuesta días de trabajo pero es el que más tarda en llegar: conviene pedirlo
hoy y hacer los otros mientras tanto.

El criterio del orden es el mismo del documento 12: **primero lo que hace
verificable lo que viene después**, y después lo que cierra lo que ya está
construido. La parte nueva se decide cuando esté decidido para qué.
