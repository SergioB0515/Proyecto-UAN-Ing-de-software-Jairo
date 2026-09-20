# 10. Evidencias de funcionamiento

## Estado actual

Aún no hay código de la aplicación implementado (ver [09. Avances del
proyecto](09-avances-proyecto.md)), por lo que este documento no cuenta
todavía con evidencia de la aplicación final.

Sí existe un **prototipo de validación**: una página interactiva construida
para confirmar, contra un archivo real de información exógena, que el
enfoque de parseo (detección de la fila de encabezados, separación del
bloque de Topes, extracción de código de concepto y renglón por expresión
regular) y el enfoque de conciliación (cruce por vínculo DIAN, exclusión de
filas autoreportadas y de retenciones) funcionan como se diseñaron. Ese
prototipo no es parte del repositorio de entrega — su función fue de
validación de diseño, documentada en [09. Avances del
proyecto](09-avances-proyecto.md) — y sus hallazgos ya están incorporados
en [03. Lógica del proyecto](03-logica-proyecto.md).

## Qué se documentará aquí una vez inicie la implementación

A medida que se completen los incrementos definidos en [05. Modelo de
desarrollo](05-modelo-desarrollo.md), esta sección se irá actualizando con:

- **Capturas de pantalla** de cada funcionalidad implementada, asociadas a
  su historia de usuario correspondiente (ver [06. Historias de
  usuario](06-historias-usuario.md)).
- **Ejemplos de peticiones y respuestas** de la API (usando la
  documentación interactiva que FastAPI genera automáticamente), mostrando
  el funcionamiento de los endpoints principales.
- **Un caso real de conciliación y de obligación de declarar**: un
  contribuyente de ejemplo con su información exógena importada, el
  resultado de obligación de declarar, el reporte de discrepancias y el
  borrador de renglones resultante.
- **Casos de prueba verificados**, indicando qué criterio de aceptación de
  cada historia de usuario quedó satisfecho.

## Plantilla sugerida por incremento

```
### Incremento 1 — Contador y contribuyentes

**Historia de usuario:** HU-01 — Registrar e iniciar sesión como contador
**Evidencia:** [captura de pantalla o video]
**Resultado:** [descripción breve de lo demostrado]
```

> Reemplazar esta plantilla con evidencia real a medida que se complete cada
> incremento.
