# 9. Avances del proyecto

## Estado a la fecha

| Frente | Estado |
|---|---|
| Presentación del proyecto (objetivo, alcance) | ✅ Completado (replanteado tras feedback del profesor; ampliado tras revisar un archivo real de exógena) |
| Modelo de desarrollo (metodología e incrementos) | ✅ Completado (reordenado: obligación de declarar, conciliación y borrador de renglones adelantados) |
| Modelo de clases y relaciones | ✅ Completado, incluyendo las entidades de configuración (`UmbralDeclaracion`, `ConceptoDian`) |
| Diagrama de flujo de uso | ✅ Completado |
| Arquitectura y stack tecnológico | ✅ Completado (propuesta; sin implementar) |
| Estructura de carpetas del proyecto | ✅ Completado (propuesta; sin implementar) |
| Historias de usuario | ✅ Completado (18 historias en 5 épicas) |
| Validación del formato real de la exógena | ✅ Completado — se analizó un archivo real (estructura de encabezado, bloque de Topes, columnas, códigos de concepto y renglones) y se generó un archivo de prueba sintético con la misma estructura para uso en `tests/` |
| Prototipo de validación (parseo + conciliación) | ✅ Completado — prototipo interactivo funcional que valida, en el navegador, el parseo del Excel real y la lógica de cruce contra datos declarados de ejemplo. Sirvió para descubrir y corregir dos supuestos del diseño (ver nota abajo) |
| **Implementación de código (Incremento 1 en adelante)** | ⏳ Pendiente de inicio |
| Evidencias de funcionamiento | ⏳ Pendiente (depende de la implementación) |

## Detalle

El proyecto se encuentra en la **fase de diseño y documentación**. Dos
hallazgos del prototipo de validación cambiaron decisiones de diseño ya
tomadas, y quedan registrados aquí para no repetir el mismo error al
implementar:

1. Se había propuesto usar el bloque de "Topes" del archivo como validación
   cruzada de la suma de los `RegistroExogena` importados. Con un archivo
   real se confirmó que el tope de Patrimonio no es una suma simple
   (sigue una fórmula propia de la DIAN que compara contra el patrimonio
   declarado el año anterior), así que esa validación cruzada se descartó
   — los Topes quedan como referencia informativa (Proceso 4 y 5 de
   [03. Lógica del proyecto](03-logica-proyecto.md)).
2. El código de concepto `1032` se reutiliza tanto para el valor de un
   ingreso como para la retención asociada a ese mismo ingreso. Agrupar
   solo por código mezclaría ambas magnitudes; el diseño de conciliación
   (Proceso 6) excluye explícitamente las filas de retención del cruce
   automático.

La **implementación** (código fuente del backend y del frontend) aún no ha
iniciado. El siguiente paso es comenzar por el **Incremento 1** (contador,
contribuyentes y patrimonio general), según lo definido en [05. Modelo de
desarrollo](05-modelo-desarrollo.md).

## Próximos pasos

1. Configurar el proyecto base (`backend/` y `frontend/`) según la
   [estructura de carpetas propuesta](02-estructura-proyecto.md).
2. Implementar el Incremento 1 y validarlo contra las historias de usuario
   HU-01 a HU-04.
3. Implementar el Incremento 2, reutilizando la lógica de parseo ya
   validada en el prototipo.
4. Conseguir los valores oficiales de UVT y topes del año gravable vigente
   para poblar `UmbralDeclaracion` antes de implementar HU-07.
5. Actualizar este documento con el avance real y capturas de pantalla en
   [10. Evidencias de funcionamiento](10-evidencias-funcionamiento.md).
