# 5. Modelo de desarrollo

## Comparación de modelos considerados

| Modelo | Características | Pertinencia para el proyecto |
|---|---|---|
| **Cascada** | Fases secuenciales: análisis, diseño, desarrollo, pruebas, despliegue. No se retrocede entre fases. | Baja. Exige requisitos 100% definidos desde el inicio, lo cual es riesgoso dado que la normatividad DIAN puede precisar detalles sobre la marcha. |
| **Espiral** | Ciclos repetidos de planeación, análisis de riesgo, desarrollo y evaluación. | Baja. Pensado para proyectos grandes y de alto riesgo; su gestión es más pesada de lo que requiere un proyecto de este alcance. |
| **Incremental** | El sistema se construye por módulos funcionales entregables, cada uno usable por sí mismo. | **Alta**. Se ajusta al proyecto porque puede dividirse en módulos claros: patrimonio, inventario, costeo y reportes. |
| **Ágil (Scrum)** | Iteraciones cortas (sprints) con entregas frecuentes y adaptación continua a cambios. | Alta. Complementa bien al modelo incremental si se requiere mayor flexibilidad de tiempos. |

## Modelo seleccionado: Incremental

Se selecciona el modelo **incremental** porque permite entregar el sistema
por partes funcionales y evaluables, reduce el riesgo de cambios tardíos en
los requisitos normativos, y facilita mostrar avances parciales durante el
desarrollo del proyecto.

## Plan de incrementos

| Incremento | Alcance | Perfil beneficiado |
|---|---|---|
| **1** | Registro de contribuyente, fuentes de ingreso y patrimonio general (`Activo`) | Funcional para asalariados desde esta etapa |
| **2** | Gestión de productos y categorías del módulo de inventario | Contribuyentes con negocio |
| **3** | Registro de movimientos de inventario (entradas y salidas) con sus documentos soporte | Contribuyentes con negocio |
| **4** | Cálculo del costo de ventas según el método de costeo configurado (PEPS o promedio ponderado) | Contribuyentes con negocio |
| **5** | Generación de reportes de cierre (kardex, saldo de inventario, resumen de patrimonio e ingresos, insumos para el formato 2517) | Todos los usuarios |

Cada incremento corresponde, a grandes rasgos, a una o más [historias de
usuario](06-historias-usuario.md), lo que permite verificar su cumplimiento
al finalizar cada etapa.

## Estado actual

Ver [09. Avances del proyecto](09-avances-proyecto.md) para el incremento en
el que se encuentra el desarrollo a la fecha.
