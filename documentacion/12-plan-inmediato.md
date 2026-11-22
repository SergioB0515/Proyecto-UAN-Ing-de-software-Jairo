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

Esto importaba antes que nada porque el siguiente trabajo de la lista
—migrar 56 columnas de dinero— es la actualización de esquema más grande que
va a tener este proyecto, y no había con qué verificarla. Ahora sí la hay.

---

## 2. Bloque 1 — Que una actualización se pueda probar

**Hecho.** Era el bloque que va primero, y ya está.

### 1.1 Prueba de actualización en el CI — **hecho**

`herramientas/prueba-actualizacion.sh`, y el trabajo `actualizacion` del CI
que lo corre en cada push y cada pull request. En vez de partir de una base
vacía:

1. Crea el esquema con el código de la **rama base** y le siembra los datos
   demo, para que la actualización ocurra sobre tablas con filas: sobre una
   tabla vacía casi cualquier migración pasa, y una columna NOT NULL sin
   valor por omisión solo falla si hay datos.
2. Corre `crear_tablas()` del commit actual encima. Esa es la migración que
   se está probando.
3. Lee y borra los datos del código anterior con el código nuevo, que
   comprueba que el actual entiende lo que escribió el anterior.
4. Vacía las tablas y corre la suite completa sobre el esquema migrado.

No hacen falta tags de versión, como decía la primera versión de este
documento: la base de comparación es la rama base del pull request, o el
commit anterior en un push. Es mejor referencia que un tag, porque es
literalmente el código que está desplegado.

No hubo que escribir una aserción por cada defecto posible. `conftest` crea
el esquema con `create_all`, que no toca una tabla que ya existe, así que si
después de migrar falta una columna o un valor de enum **las pruebas fallan
igual que falló producción**. La suite ya era la verificación; lo que faltaba
era darle una base con historia.

Validada en los dos sentidos, que es lo que hace que sirva:

| Código bajo prueba | Resultado |
|---|---|
| `7436f97`, el commit que tenía el defecto del enum | 10 pruebas fallan, entre ellas los estados `NO_LO_TENGO` y `NO_ENTIENDO` |
| `main` actual | 579 en verde |

Es decir: con este trabajo en el CI, el 500 no habría llegado a Render.

Un detalle que salió al construirla, y que vale anotar: `borrar_demo` no
borra las tablas de parámetros fiscales, porque son datos de referencia
globales y en producción está bien que se queden. En la suite estorban —hay
pruebas que siembran sus propios parámetros y asumen que no hay otros—, de
ahí el paso de vaciar las tablas antes de correrla. El esquema viene de la
actualización; los datos, no.

### 1.2 Alembic — **hecho**

Las migraciones eran `ALTER TABLE` a mano dentro de `database.py`
(`_agregar_columnas_si_faltan`, `_sincronizar_enums`,
`_migrar_periodo_en_activos_y_fuentes`), y cada una hubo que escribirla
*después* de que el defecto apareciera en producción.

Ahora el esquema lo construyen las revisiones de `backend/alembic/versions/`.
El detalle operativo está en `backend/alembic/README.md`; acá va lo que tuvo
que decidirse.

**Una corrección a lo que decía este documento.** Decía que los helpers se
irían convirtiendo en revisiones «una por una». Está mal, y se vio al
construirlo: una base nueva sale completa de la revisión base, así que una
revisión que agregara `fecha_corte` a `reportes_exogena` sería un no-op o un
error de columna duplicada. Esos helpers no son historia por registrar; son
alcance para bases que ya existen.

Lo que se hizo:

- **Una revisión base** con el esquema completo de hoy, generada con
  `--autogenerate` contra una base vacía: 35 tablas y 21 tipos enum.
- **Los helpers degradados a puente de una sola vez.** `crear_tablas()`
  distingue tres casos, y la distinción importa porque sellar una base sin su
  esquema la rompe para siempre:

  | Base | Qué hace |
  |---|---|
  | Vacía | Las revisiones la construyen entera |
  | Con esquema y sin sellar (la desplegada) | El puente la lleva al baseline, la sella y aplica el resto |
  | Ya sellada | Aplica las revisiones que falten |

- **Una comprobación de deriva**, `herramientas/comprobar_revisiones.py`:
  crea una base vacía, le aplica `alembic upgrade head` y compara el
  resultado contra los modelos. Sin esto Alembic es ceremonia: si alguien
  cambia un modelo y no escribe la revisión, le funciona en su máquina
  —donde la base nace completa— y se rompe en el despliegue. Es el mismo
  defecto de siempre con otra herramienta.
- **`compare_type` encendido** y `compare_server_default` apagado. Lo primero
  hace falta para el bloque 2, la migración de dinero: sin eso
  `--autogenerate` no ve un cambio de `float` a `NUMERIC`. Lo segundo, porque
  los parches viejos agregaron columnas con DEFAULT en la base que los
  modelos no declaran, y encendido el comparador los reportaría como
  diferencia en cada corrida hasta volverse inútil.

Verificado en los tres casos. El que importaba era el de la base desplegada:
una base anterior a Alembic con datos sembrados queda sellada en la revisión
base, con los 6 contribuyentes intactos y **sin diferencias** contra los
modelos. La suite completa pasa sobre ella: 579.

**El orden 1.1 → 1.2 no era negociable** y se respetó. Alembic sin la prueba
de actualización es otra forma de escribir migraciones que nadie verifica;
con la prueba primero, cada paso de la adopción se comprobó en vez de
suponerse.

---

## 3. Bloque 2 — El dinero en `Decimal` — **hecho**

Eran 56 campos monetarios en `float`. Ya no queda ninguno: el dinero está en
`NUMERIC(18,2)` y las cantidades de inventario en `NUMERIC(18,3)`, en los
siete módulos que faltaban.

`float` no representa exactamente los decimales de la contabilidad: `0.1 +
0.2` da `0.30000000000000004`. El error es diminuto y se acumula sumando
renglones, así que los totales dejan de cuadrar al centavo. Un contador que
ve un descuadre de $0,03 deja de confiar en todo lo demás, y tiene razón.

### Cómo se hizo

- **`core/dinero.py`** centraliza el tipo: `campo_dinero()`,
  `campo_cantidad()`, `campo_uvt()`, `a_decimal()` y `redondear_pesos()`. Sin
  eso, `Numeric(18, 2)` quedaba escrito 56 veces y cambiar la precisión sería
  una cacería.
- **Las cantidades llevan tres decimales**, no dos. El costo unitario sale de
  dividir valor entre cantidad: recortar la cantidad a dos decimales mete el
  error por la puerta de atrás.
- **`costeo.py` casi no cambió**, y vale decir por qué: ya calculaba en
  `Decimal` internamente y convertía a `float` al entrar y al salir, porque la
  base y la API lo eran. Hacía el redondeo bien y lo tiraba a la basura al
  devolverlo. La migración fue dejar de convertir de vuelta.
- **Se borraron 20 conversiones de frontera** (`Decimal(str(...))` y
  `float(...)`) que existían para cruzar entre las dos convenciones. Eran el
  síntoma, no la solución.

### Tres cosas que no estaban previstas

1. **Las dos convenciones también estaban en el cable, no solo en la base.**
   Pydantic serializa `Decimal` como cadena JSON, así que la API devolvía el
   dinero como número en los módulos viejos (`4000000`) y como cadena en los
   nuevos (`"4000000.00"`). La migración unifica eso; no lo introduce. Hubo
   que actualizar 35 aserciones de las pruebas, que comparaban contra números.
2. **Tres sumas del frontend quedaban rotas.** `PatrimonioView` hacía
   `s + a.valor` en tres `reduce`, y `+` con una cadena concatena en vez de
   sumar: habría mostrado «04000000.001500000.00». El resto de los operadores
   de JavaScript convierten solos; la suma es la única que muerde.
3. **`redondear_pesos` ya existía** en `liquidacion/motor.py`, y yo escribí la
   misma función otra vez. Ahora hay una sola, en `core/dinero.py`, que
   `motor.py` vuelve a exportar porque dentro de liquidación se usa en 18
   sitios. De paso: la primera versión del helper se llamaba `pesos()`, que
   choca con `core.formato.pesos()`, que convierte a texto para mostrar. En un
   archivo que importaba las dos ganaba la última, y la base terminó
   rechazando un `'$14.850.000'` en una columna numérica. Las pruebas lo
   atraparon; leyendo el código no se veía.

### Verificación

- **579 pruebas en verde** contra Postgres, en base nueva y en base migrada.
- Las revisiones reproducen los modelos sin diferencias.
- La prueba de actualización migra los 56 campos sobre una base **con datos**
  partiendo del código desplegado, y los valores quedan idénticos: los activos
  sumaban 751.000.000 antes y 751.000.000,00 después; la exógena,
  2.346.710.000 en los 38 registros. Postgres convierte `DOUBLE PRECISION` a
  `NUMERIC` con un cast implícito, así que las filas existentes se migran
  solas.

Lo que no se puede arreglar: lo que ya se guardó con error de representación
se queda con ese error redondeado a centavos. No se reconstruye lo perdido,
solo se deja de perder más.

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
| ~~1~~ | ~~Prueba de actualización en el CI~~ **hecho** | — | — |
| ~~2~~ | ~~Alembic~~ **hecho** | — | — |
| ~~3~~ | ~~56 campos de dinero a `Decimal`~~ **hecho** | — | — |
| 4 | Historias de usuario del portal (HU-28+) y actualizar el 11 | 1 d | Bajo |
| 5 | Consolidar las tablas laterales de liquidación | 1 d | Bajo |
| 6 | Simulador de planeación tributaria | 5–7 d | Bajo |

Queda alrededor de una semana: los bloques 1 y 2 están hechos, que eran el
riesgo y la mitad del esfuerzo. En paralelo y desde el primer día: pedir las dos declaraciones
reales.

El criterio detrás del orden es uno solo: **primero lo que hace verificable
lo que viene después.** Los bloques 1 y 2 no agregan una sola pantalla y son
lo que permite que el bloque 4 no se construya encima de cimientos que nadie
ha probado.
