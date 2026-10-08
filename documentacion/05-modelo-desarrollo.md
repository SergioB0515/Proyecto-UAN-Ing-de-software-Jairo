# 5. Modelo de desarrollo

## Comparación de modelos considerados

| Modelo | Características | Pertinencia para el proyecto |
|---|---|---|
| **Cascada** | Fases secuenciales: análisis, diseño, desarrollo, pruebas, despliegue. No se retrocede entre fases. | Baja. Exige requisitos 100% definidos desde el inicio, lo cual es riesgoso dado que el formato exacto del archivo de exógena y la normatividad DIAN pueden precisar detalles sobre la marcha. |
| **Espiral** | Ciclos repetidos de planeación, análisis de riesgo, desarrollo y evaluación. | Baja. Pensado para proyectos grandes y de alto riesgo; su gestión es más pesada de lo que requiere un proyecto de este alcance. |
| **Incremental** | El sistema se construye por módulos funcionales entregables, cada uno usable por sí mismo. | **Alta**. Se ajusta al proyecto porque puede dividirse en módulos claros: contribuyentes, exógena, conciliación, inventario y reportes. |
| **Ágil (Scrum)** | Iteraciones cortas (sprints) con entregas frecuentes y adaptación continua a cambios. | Alta. Complementa bien al modelo incremental si se requiere mayor flexibilidad de tiempos. |

## Modelo seleccionado: Incremental

Se selecciona el modelo **incremental** porque permite entregar el sistema
por partes funcionales y evaluables, reduce el riesgo de cambios tardíos en
los requisitos normativos, y facilita mostrar avances parciales durante el
desarrollo del proyecto.

## Plan de incrementos

El orden se replanteó respecto a la versión original del proyecto: la
importación de exógena, la verificación de obligación de declarar, la
conciliación y el borrador de renglones —los requisitos centrales
señalados por el profesor y los que más valor agregan a un contador real—
se adelantan al segundo y tercer incremento, en vez de dejarse para el
final. El módulo de inventario, que antes era el más desarrollado, pasa a
un orden de prioridad posterior.

| Incremento | Alcance | Por qué en este orden |
|---|---|---|
| **1** | Autenticación del contador; registro y gestión de contribuyentes; registro de patrimonio y fuentes de ingreso | Es la base mínima de datos necesaria para poder conciliar algo en el incremento 3 |
| **2** | Importación del archivo de información exógena (carga, parseo con `pandas`, `RegistroExogena`, catálogo de conceptos DIAN); verificación de obligación de declarar | Sin datos de exógena importados no hay nada que conciliar; la verificación de obligación es una extensión barata de la misma importación (reutiliza los "Topes" ya extraídos) y es de las primeras cosas que un contador necesita saber de un cliente |
| **3** | Motor de conciliación y vista de resultado; borrador de valores sugeridos por renglón | Es el requisito explícito del profesor, y el borrador de renglones reutiliza el mismo parseo — ambos deben quedar demostrables antes que el resto |
| **4** | Módulo de inventario: categorías, productos, movimientos (entradas/salidas), costeo PEPS/promedio ponderado | Se mantiene del alcance original, pero como segunda prioridad frente a la conciliación |
| **5** | Cierre de periodo fiscal, reportes consolidados (kardex, saldo de inventario, resumen de patrimonio e ingresos, reporte de conciliación) y panel de cartera | Cierre del sistema; el panel de cartera integra la salida de todos los contribuyentes del contador, así que necesita que los incrementos anteriores ya existan para varios contribuyentes |
| **6** | Seguridad y trazabilidad: bloqueo por intentos fallidos y registro de accesos, política y cambio de contraseña, auditoría de acciones, validación del archivo subido, cabeceras de seguridad HTTP | La app maneja información tributaria de terceros; con el alcance funcional completo, se aborda la capa de auditoría que el proyecto había dejado como extensión |
| **7** | Calidad de vida: corrección y eliminación de registros, copia de activos entre años, declarar desde la conciliación | Reduce la digitación repetida y permite corregir errores, lo que más fricción genera en el uso diario |

Si el cronograma se ajusta durante el semestre, el incremento 4
(inventario) sigue siendo el candidato natural a recortar o dejar como
alcance opcional — no es el requisito que motivó el replanteamiento del
proyecto. La capa de auditoría/seguridad mencionada en
[01. Presentación del proyecto](01-presentacion-proyecto.md) se abordó en
el incremento 6, una vez completo el alcance funcional (salvo el cifrado en
reposo, que sigue fuera de alcance).

Cada incremento corresponde, a grandes rasgos, a una o más [historias de
usuario](06-historias-usuario.md), lo que permite verificar su cumplimiento
al finalizar cada etapa.

## Estado actual

Ver [09. Avances del proyecto](09-avances-proyecto.md) para el incremento en
el que se encuentra el desarrollo a la fecha.
