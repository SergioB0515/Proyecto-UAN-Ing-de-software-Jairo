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
| Backend — Incremento 1 (HU-01 a HU-04) | ✅ Implementado y probado |
| Backend — Incremento 2 (HU-05 a HU-07) | ✅ Implementado y probado |
| Backend — Incremento 3 (HU-08 a HU-10) | ✅ Implementado y probado |
| Backend — Incremento 4 (HU-11 a HU-14) | ✅ Implementado y probado |
| Backend — Incremento 5 (HU-15 a HU-18) | ✅ Implementado y probado |
| Frontend | ⏳ Pendiente (solo esqueleto de carpetas) |
| Evidencias de funcionamiento | ⏳ Pendiente (capturas por historia de usuario) |

## Detalle

El backend tiene implementados los cinco incrementos, con 114 pruebas
automáticas que corren contra una base de datos PostgreSQL real (ver
[backend/README.md](../backend/README.md) para los endpoints y cómo
correrlas).

Dos hallazgos del prototipo de validación cambiaron decisiones de diseño
y quedaron incorporados en la implementación:

1. Se había propuesto usar el bloque de "Topes" del archivo como validación
   cruzada de la suma de los `RegistroExogena` importados. Con un archivo
   real se confirmó que el tope de Patrimonio no es una suma simple
   (sigue una fórmula propia de la DIAN que compara contra el patrimonio
   declarado el año anterior), así que esa validación cruzada se descartó
   — los Topes quedan como referencia informativa (Proceso 4 y 5 de
   [03. Lógica del proyecto](03-logica-proyecto.md)).
2. El código de concepto `1032` se reutiliza tanto para el valor de un
   ingreso como para la retención asociada a ese mismo ingreso. Agrupar
   solo por código mezclaría ambas magnitudes; el motor de conciliación
   excluye las filas de retención del cruce automático (hay una prueba
   específica para este caso en `tests/test_conciliacion.py`).

Decisiones tomadas durante el incremento 4:

- El costo de cada salida **no se almacena**: el kardex se recalcula
  reproduciendo los movimientos en orden cronológico, de modo que una
  compra registrada con fecha anterior corrige el costo de las ventas
  posteriores sin dejar datos guardados desactualizados.
- Una salida se rechaza si deja el stock en negativo en cualquier punto
  de la línea de tiempo, no solo al final.
- El método de costeo de un producto queda bloqueado una vez tiene
  movimientos.

Decisiones tomadas durante el incremento 5:

- Los periodos se cierran en orden de año y solo se puede reabrir el
  último cerrado, porque el saldo inicial de inventario de un año depende
  del cierre del anterior.
- El cierre registra el inventario final como `Activo` de tipo
  `INVENTARIO`, y el patrimonio solo cuenta el del último cierre (el de
  años anteriores ya está contenido en el saldo inicial del siguiente).
  Ese tipo de activo ya no se puede registrar a mano.
- Lo que hizo cada cierre se guarda en `CierrePeriodo`, para poder
  deshacerlo al reabrir.

## Próximos pasos

1. Asociar cada `FuenteIngreso` y `Activo` a un `PeriodoFiscal` (criterio
   de HU-03 aún no cubierto; requiere recrear esas tablas al no haber
   migraciones). Mientras tanto el resumen lo advierte en `avisos`.
2. Frontend en Vue 3 sobre los endpoints ya disponibles.
3. Registrar capturas y casos verificados en
   [10. Evidencias de funcionamiento](10-evidencias-funcionamiento.md).
