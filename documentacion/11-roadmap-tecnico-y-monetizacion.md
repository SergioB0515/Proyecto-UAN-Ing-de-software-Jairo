# 11. Roadmap técnico y modelo de monetización

> Documento de estado y planeación, con corte al **3 de noviembre de 2026**.
> Las cifras de mercado y los parámetros tributarios citados aquí se
> verificaron contra fuente ese día; los tributarios cambian cada año y las
> de mercado cada pocos meses.

---

## 0. Para qué sirve este documento y para qué no

Sirve para decidir qué construir después y con qué criterio. No es un plan de
negocio para levantar inversión ni una promesa de que el producto esté listo
para vender: dice, con nombre propio, qué falta para eso.

Las estimaciones de esfuerzo están en días de trabajo de **una persona con el
nivel actual del equipo**, no de un equipo senior. Son estimaciones, y las
estimaciones de software se quedan cortas; tómelas como orden de magnitud.

---

## 1. Estado real del proyecto

| Métrica | Valor |
|---|---|
| Líneas de código (backend + frontend) | ~18.700 |
| Módulos del backend | 12 |
| Pruebas automatizadas | 260, todas en verde |
| Historias de usuario con evidencia | 27 (HU-01 a HU-27) |
| Despliegue | Docker + Render, un solo contenedor |
| CI | GitHub Actions |

### Lo que está bien hecho

- **Separación por módulos con frontera clara.** Cada módulo tiene modelos,
  servicios, router y su propio README. Es la decisión de arquitectura que
  permitió agregar la liquidación sin tocar nada de lo anterior.
- **Multi-tenencia por contador desde el día uno.** Todo consulta por
  `contador_id`, y hay pruebas que verifican que un contador no alcanza los
  datos de otro. Esto es muy difícil de agregar después; está bien que esté.
- **Auditoría transversal.** El middleware registra toda escritura, y una
  prueba falla si se agrega un endpoint que modifica y no se declara auditado.
  Esa prueba atrapó los endpoints nuevos de liquidación mientras se escribían:
  es el tipo de guardarraíl que vale más que cien líneas de documentación.
- **Honestidad en las salidas.** `ResultadoObligacion` y `BorradorRenglones`
  ya traían advertencias sobre lo que no evalúan. Es exactamente el
  posicionamiento correcto y hay que mantenerlo.
- **Seguridad razonable para el alcance.** Argon2, JWT, bloqueo por intentos,
  cabeceras de seguridad, validación de tipo real de archivo subido.

### Lo que está mal y hay que arreglar

1. **El dinero se guarda en `float`.** Hay 61 campos monetarios en `float` y
   cero `Decimal` en los módulos anteriores a esta iteración. En software
   contable es un defecto: el error de representación binaria se acumula y los
   totales dejan de cuadrar al centavo. Un contador que vea un descuadre de
   $0,03 en un informe deja de confiar en todo lo demás.
2. **No hay migraciones.** El esquema se crea con `SQLModel.metadata.create_all`
   y los cambios se parchan con `ALTER TABLE` a mano dentro de `database.py`.
   Funciona hoy y deja de funcionar en cuanto haya datos reales que no se
   puedan perder.
3. **Un contador es un usuario, no una firma.** No hay organización, ni roles,
   ni asistentes. Las 4.665 firmas contables del país —que son los clientes que
   pagan más— necesitan varios usuarios sobre la misma cartera.
4. **El catálogo de conceptos de la DIAN no está cargado.** La clasificación de
   ingresos por cédula se sugiere con palabras del concepto, no con el código.
   Funciona, pero es menos fiable de lo que podría ser.

---

## 2. Lo que se construyó en esta iteración

El hueco que se cerró: **la aplicación conciliaba la exógena pero no liquidaba
el impuesto.** El «borrador por renglón» sumaba la columna *«Uso declaración
Sugerida»* del archivo de la DIAN y la agrupaba. Es un auxiliar de
transcripción útil, pero el contador tenía que liquidar aparte, normalmente en
Excel. Ahí es donde se le va el tiempo y donde se cometen los errores.

### `modulos/parametros/tablas_oficiales.py`

Parámetros tributarios versionados por año gravable, **cada uno con la norma
que lo fija**. Años 2023 a 2026 cargados bajo el régimen de la Ley 2277 de 2022.

| Parámetro | Valor | Norma |
|---|---|---|
| UVT 2026 | $52.374 | Resolución DIAN 000238 del 15-12-2025 |
| UVT 2025 | $49.799 | Resolución DIAN de 2025 |
| UVT 2024 | $47.065 | Resolución DIAN 000187 del 28-11-2023 |
| UVT 2023 | $42.412 | Resolución DIAN 001264 del 18-11-2022 |
| Tabla de tarifas | 7 tramos, 0 % a 39 % | Art. 241 ET (Ley 2010 de 2019, art. 34) |
| Límite rentas exentas y deducciones | 40 %, tope 1.340 UVT | Art. 336 num. 3 ET (Ley 2277 de 2022, art. 7) |
| Dependientes | 72 UVT c/u, hasta 4, fuera del límite | Art. 336 num. 3 ET |
| Deducción 1 % de compras | tope 240 UVT, fuera del límite | Art. 336 num. 5 ET |
| Renta exenta de trabajo | 25 %, tope 790 UVT | Art. 206 num. 10 ET |
| Renta exenta de pensiones | 1.000 UVT mensuales | Art. 206 num. 5 ET |
| Ganancia ocasional | 15 % (20 % loterías) | Arts. 313 a 317 ET (Ley 2277 de 2022) |
| Descuento por dividendos | 19 % del exceso de 1.090 UVT | Art. 254-1 ET (Ley 2277 de 2022, art. 12) |
| Renta presuntiva | 0 % | Art. 188 ET (Ley 2010 de 2019, art. 78) |
| Topes para declarar | 4.500 UVT patrimonio; 1.400 UVT los demás | Arts. 592 y 594-3 ET; DUR 1625 de 2016 |

**Nota normativa:** el proyecto de ley de financiamiento radicado en julio de
2026 fue archivado por las comisiones económicas del Congreso, así que el
régimen de la Ley 2277 de 2022 sigue vigente. Si una reforma se aprueba, se
agrega un bloque nuevo con su propio `regimen` y los años anteriores se siguen
liquidando bien. Ese es el punto de haber separado parámetros de lógica.

### `modulos/liquidacion/`

- **`motor.py`** — El cálculo. Funciones puras sobre `Decimal`, sin base de
  datos. Depura la cédula general, aplica el límite del art. 336, calcula la
  cédula de pensiones y la de dividendos, aplica la tabla del art. 241, liquida
  ganancias ocasionales a su tarifa propia, aplica descuentos, calcula el
  anticipo del art. 807 y cierra con saldo a pagar o a favor.
- **Trazabilidad obligatoria.** Cada renglón sale con la fórmula que lo produjo
  y la norma que lo respalda. Una prueba falla si aparece un renglón sin
  rastro. Es lo que convierte el resultado en un papel de trabajo defendible
  frente a una revisión, en vez de un número de una caja negra.
- **`clasificador.py`** — Sugiere la cédula de cada ingreso. Sugiere, no
  decide: lo que el contador no confirme **queda fuera del cálculo** y aparece
  como diagnóstico. Adivinar la cédula cambia el impuesto, y esa no es una
  decisión del software.
- **Diagnósticos accionables.** Cuando el límite del 40 % recorta, el motor
  dice cuánto recortó, cuál de las tres cifras mandó y que el exceso no se
  traslada a otros años.
- **Aproximación al múltiplo de mil** (art. 577 ET) solo en el valor que se
  transcribe, nunca en los cálculos intermedios.
- **63 pruebas nuevas**, 45 de ellas sobre el motor puro, que recalculan cada
  tramo de la tabla con la fórmula impresa en el Estatuto en vez de comparar
  contra la salida del propio motor.

### Lo que el motor no hace, a propósito

- No liquida años sin parámetros cargados: lanza un error con la lista de años
  disponibles. Una cifra equivocada que parece correcta es peor que un error.
- No pone los números de renglón del formulario 210. Los fija la resolución de
  la DIAN de cada año y hay que mapearlos antes de transcribir.
- No presenta la declaración. No existe API pública de la DIAN para eso.

---

## 3. Deuda técnica, priorizada

| # | Tarea | Esfuerzo | Riesgo | Por qué importa |
|---|---|---|---|---|
| 1 | Migrar los 61 campos de dinero de `float` a `Decimal`/`NUMERIC(18,2)` | 3–5 días | **Alto** | Toca todos los módulos y las 260 pruebas. Es el defecto más serio para software contable. |
| 2 | Alembic para migraciones versionadas | 1–2 días | Bajo | Sin esto no se puede evolucionar el esquema con datos reales en producción. |
| 3 | Mover la cédula a columna de `fuentes_ingreso` y retirar `clasificaciones_ingreso` | 1 día | Bajo | La tabla aparte fue una decisión de no romper nada a tres semanas de la entrega; el diseño correcto es la columna. |
| 4 | Capa de organización: firma → contadores → roles | 4–6 días | Medio | Las 4.665 firmas del país no son un contador solo. Es el techo comercial actual. |
| 5 | Cargar el catálogo de conceptos de la DIAN por resolución anual | 2–3 días | Bajo | Clasificar por código es más fiable que por palabras del concepto. |
| 6 | Mapeo renglón → formulario 210 oficial, versionado por resolución | 2 días | Bajo | Hoy los códigos son propios y el contador tiene que mapear a mano. |
| 7 | Respaldos, política de retención y cifrado en reposo | 2–3 días | Medio | El art. 632 ET obliga a conservar soportes 5 años. Si se pierde la base, se pierde el cliente. |
| 8 | Observabilidad: logs estructurados, errores, métricas | 2 días | Bajo | Sin esto, un error en producción se depura adivinando. |
| 9 | Límite de peticiones y segundo factor | 2 días | Bajo | Datos tributarios de terceros justifican más que una contraseña. |

**El orden importa.** El 1 y el 2 van antes que cualquier módulo nuevo: migrar
`float` a `Decimal` con tres módulos más encima cuesta el triple.

---

## 4. Módulos faltantes, por valor real para un contador

El criterio de orden no es «qué falta», es **cuánto tiempo le ahorra al
contador y con qué frecuencia**. Un módulo que se usa una vez al año vale
menos que uno que se usa cada mes, aunque suene más ambicioso.

### Prioridad alta

| Módulo | Esfuerzo | Por qué |
|---|---|---|
| **Retención en la fuente** (procedimientos 1 y 2, certificados) | 8–12 días | Es **mensual**, no anual. Convierte el producto de estacional a recurrente, que es la diferencia entre un pico en agosto y un ingreso de doce meses. |
| **Exógena como reportante** (formatos 1001, 1003, 1005, 1007, 1008, 1009, 1012 y XML de la DIAN) | 15–20 días | Hoy la app *lee* la exógena del contribuyente. Generar la que el cliente debe *reportar* es trabajo que el contador hace a mano todos los años y por el que cobra. |
| **Comparación patrimonial** (arts. 236 a 239 ET) | 4–6 días | Detecta que el patrimonio creció más que la renta declarada, que es exactamente lo que la DIAN cruza. Diferenciador real y barato: ya hay histórico por año. |

### Prioridad media

| Módulo | Esfuerzo | Por qué |
|---|---|---|
| **Portal del contribuyente** (que el cliente suba sus propios soportes) | 10–15 días | El mayor costo del contador es perseguir documentos. Ataca el dolor, no la tarea. |
| **Simulador de planeación tributaria** | 5–7 días | «¿Cuánto bajo el impuesto si aporto 20 millones a AFC?» Con el motor ya hecho, es recalcular con insumos alterados. |
| **Firma electrónica y generación del archivo para MUISCA** | 8–12 días | Hasta donde llega lo posible: la presentación en sí es manual. |
| **Declaraciones de IVA e ICA** | 12–18 días c/u | Recurrentes, pero mercado muy atendido. |

### Prioridad baja o descartadas

- **Facturación electrónica y nómina electrónica.** Mercado saturado por Siigo,
  Alegra y World Office, con habilitación ante la DIAN como barrera. Entrar ahí
  es competir de frente con empresas de cientos de empleados.
- **Contabilidad completa con NIIF.** Años de trabajo. No es el camino.
- **App móvil.** El profesor pidió explícitamente web. Un contador trabaja en
  pantalla grande con dos monitores.

---

## 5. Por qué la DIAN no es el cliente

Conviene decirlo sin rodeos, porque orienta mal todo lo demás:

1. **La DIAN es la autoridad tributaria, no un comprador de software para
   contadores.** Ella *publica* la plataforma (MUISCA) a la que los contadores
   se conectan. No compra herramientas para que terceros declaren mejor.
2. **Venderle algo a la DIAN sería contratación estatal**, por SECOP II, con
   requisitos de experiencia acreditada, capacidad financiera, pólizas y
   habilitación jurídica que ningún proyecto de dos estudiantes cumple, por
   bueno que sea el código.
3. **No existe API pública de la DIAN para presentar declaraciones.** Se
   presenta en MUISCA con el instrumento de firma electrónica. Cualquier
   promesa de «presentación automática» sería falsa.
4. **«Infalible» no es alcanzable y afirmarlo es exposición legal.** La
   responsabilidad de la declaración es del contribuyente y del contador que la
   firma (art. 581 ET). Ningún producto del mercado se vende como infalible.

Nada de esto hace el proyecto menos valioso. Lo reubica: **el cliente es el
contador**, y ese mercado existe y paga.

---

## 6. El mercado real y cómo se cobra

### Tamaño

| Dato | Cifra | Fuente |
|---|---|---|
| Contadores públicos inscritos en Colombia | 334.685 | Junta Central de Contadores, rendición de cuentas, corte junio de 2025 |
| Sociedades prestadoras de servicios contables | 4.665 | Misma fuente |

No todos son mercado. Un corte realista: contadores independientes y firmas
pequeñas que atienden carteras de 20 a 300 personas naturales. Aun tomando el
1 % de los inscritos, son más de 3.000 clientes potenciales.

### Lo que cobra la competencia (precios mensuales, 2026)

| Producto | Rango mensual |
|---|---|
| Alegra Contabilidad | $69.900 – $279.900 |
| Siigo Nube | ~$146.000 – ~$208.000 |
| Loggro Pymes | $108.990 – $279.990 |
| World Office Cloud / Helisa | Por cotización |

Son productos de **contabilidad general**, no de renta de personas naturales.
Esa es la grieta: ninguno resuelve bien conciliar exógena contra lo registrado y
liquidar el 210 de una cartera de cien personas.

### Modelo de cobro propuesto

Cobrar **por contribuyente en la cartera y por año gravable**, no por usuario.
Es la unidad que el contador entiende, porque es exactamente como él le factura
a su cliente, y escala con el valor que recibe.

| Plan | Contribuyentes | Precio mensual sugerido |
|---|---|---|
| Independiente | hasta 25 | $59.000 |
| Profesional | hasta 100 | $149.000 |
| Firma | hasta 400, varios usuarios | $390.000 |
| Firma grande | más de 400 | Por cotización |

Son precios de referencia construidos para quedar por debajo de la
competencia general y por encima de lo gratuito. **Hay que validarlos
hablando con contadores antes de fijarlos**, no deducirlos de una tabla.

### Por qué un contador cambiaría

El argumento de venta no es «tenemos más módulos». Es tiempo:

> Conciliar la exógena de un contribuyente contra lo que tiene registrado y
> liquidar su 210 a mano toma entre 40 y 90 minutos. Con cien clientes en
> temporada, son de 70 a 150 horas. Esta herramienta deja el borrador liquidado
> con cada renglón trazado a su norma, y el contador revisa y firma.

Ese número hay que medirlo con contadores reales antes de ponerlo en una
propuesta comercial. Es la métrica que decide si el producto se vende.

### Estacionalidad: el problema del modelo

La declaración de renta de personas naturales se presenta entre agosto y
octubre. Un producto que solo sirve para eso tiene nueve meses muertos y una
tasa de cancelación brutal en noviembre. **Por eso el módulo de retención en la
fuente es prioridad alta y no media**: es mensual, y es lo que vuelve el
ingreso recurrente. Sin él, no hay negocio SaaS, hay un servicio de temporada.

---

## 7. Requisitos legales antes de cobrar el primer peso

Esto no es opcional y no está hecho:

1. **Ley 1581 de 2012 (protección de datos personales).** La aplicación trata
   datos de terceros —los clientes del contador— que ni siquiera son usuarios.
   Hace falta política de tratamiento publicada, aviso de privacidad,
   autorización, procedimiento de consultas y reclamos, y medidas de seguridad
   documentadas.
2. **RNBD ante la SIC.** El registro es obligatorio para sociedades con activos
   superiores a 100.000 UVT, así que al arrancar probablemente no aplique —pero
   el resto de las obligaciones de la Ley 1581 sí, desde el primer cliente.
3. **Contrato de términos de servicio** que diga explícitamente que la
   herramienta es de apoyo y que la responsabilidad de la declaración es del
   contribuyente y del contador que firma (art. 581 ET), con limitación de
   responsabilidad.
4. **Figura jurídica.** Facturar requiere RUT con la actividad y, para vender a
   firmas, lo normal es una SAS.
5. **Respaldos y continuidad.** Si un contador pierde la información de su
   cartera en agosto, el daño no es reputacional, es indemnizable.

---

## 8. Qué le falta para ser trabajo de grado

El coordinador va a evaluar si la idea aplica. Lo que diferencia un proyecto de
curso bueno de un trabajo de grado no es el tamaño, es que haya una
**pregunta de investigación con resultado medible**. Tres opciones que el
estado actual ya soporta:

1. **Validación empírica del motor.** Liquidar N declaraciones reales
   —anonimizadas— con la herramienta y con el método manual del contador, y
   medir diferencia de resultado y tiempo. Es la tesis más fuerte: produce un
   número defendible y usa lo que ya está construido.
2. **Detección de inconsistencias exógena–declaración.** Medir cuántas
   discrepancias encuentra la conciliación automática frente a la revisión
   manual sobre el mismo conjunto. Conecta con la idea de la capa supervisora.
3. **Arquitectura de parámetros versionados para software tributario.** Menos
   atractiva, pero es un problema real y poco tratado: cómo diseñar un sistema
   que no quede desactualizado con cada reforma. El módulo de parámetros es la
   implementación de referencia.

La opción 1 es la que tiene más probabilidad de ser aceptada, porque tiene
metodología clara, datos obtenibles y un resultado que se puede graficar.

---

## 9. Lo primero que haría

En este orden, y nada más hasta terminar cada uno:

1. **Antes de la entrega de noviembre:** probar la liquidación con dos o tres
   declaraciones reales que un contador conocido ya haya presentado, y comparar
   cifra contra cifra. Si cuadra, es la mejor diapositiva de la sustentación.
   Si no cuadra, hay que saberlo antes y no después.
2. **Después de la entrega:** Alembic y la migración a `Decimal`. Sin eso no se
   puede poner nada en producción con datos reales.
3. **Luego:** retención en la fuente, para que el producto tenga uso los doce
   meses del año.
4. **En paralelo, desde ya:** hablar con cinco contadores. No para venderles;
   para preguntarles en qué se les va el tiempo. Es probable que la respuesta
   cambie este orden, y esa información vale más que cualquier módulo que se
   pueda escribir esta semana.
