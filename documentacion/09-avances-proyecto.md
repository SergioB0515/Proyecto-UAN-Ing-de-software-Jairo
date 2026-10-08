# 9. Avances del proyecto

## Estado a la fecha

| Frente | Estado |
|---|---|
| Presentación del proyecto (objetivo, alcance) | ✅ Completado (replanteado tras feedback del profesor; ampliado tras revisar un archivo real de exógena) |
| Modelo de desarrollo (metodología e incrementos) | ✅ Completado (reordenado: obligación de declarar, conciliación y borrador de renglones adelantados) |
| Modelo de clases y relaciones | ✅ Completado, incluyendo las entidades de configuración (`UmbralDeclaracion`, `ConceptoDian`) |
| Diagrama de flujo de uso | ✅ Completado |
| Arquitectura y stack tecnológico | ✅ Completado e implementado |
| Estructura de carpetas del proyecto | ✅ Completado e implementado |
| Historias de usuario | ✅ Completado (24 historias en 7 épicas) |
| Validación del formato real de la exógena | ✅ Completado — se analizó un archivo real (estructura de encabezado, bloque de Topes, columnas, códigos de concepto y renglones) y se generó un archivo de prueba sintético con la misma estructura para uso en `tests/` |
| Prototipo de validación (parseo + conciliación) | ✅ Completado — prototipo interactivo funcional que valida, en el navegador, el parseo del Excel real y la lógica de cruce contra datos declarados de ejemplo. Sirvió para descubrir y corregir dos supuestos del diseño (ver nota abajo) |
| Backend — Incremento 1 (HU-01 a HU-04) | ✅ Implementado y probado |
| Backend — Incremento 2 (HU-05 a HU-07) | ✅ Implementado y probado |
| Backend — Incremento 3 (HU-08 a HU-10) | ✅ Implementado y probado |
| Backend — Incremento 4 (HU-11 a HU-14) | ✅ Implementado y probado |
| Backend — Incremento 5 (HU-15 a HU-18) | ✅ Implementado y probado |
| Backend — HU-03 completa (activos y fuentes de ingreso por periodo) | ✅ Implementado y probado |
| Edición y eliminación de contribuyentes, activos e ingresos | ✅ Implementado y probado (backend y frontend) |
| Incremento 6 — Seguridad y trazabilidad (HU-19 a HU-21) | ✅ Implementado y probado (backend y frontend) |
| Incremento 7 — Calidad de vida (HU-22 a HU-24) | ✅ Implementado y probado (backend y frontend) |
| Integración continua (GitHub Actions) | ✅ Pruebas del backend con PostgreSQL y compilación del frontend en cada push |
| Frontend (Vue 3 + Vite + Tailwind) — todas las historias | ✅ Implementado y verificado de punta a punta en el navegador |
| Evidencias de funcionamiento | ✅ Capturas por historia de usuario ([10](10-evidencias-funcionamiento.md)) |

## Detalle

El backend tiene implementados los cinco incrementos, con 152 pruebas
automáticas que corren contra una base de datos PostgreSQL real (ver
[backend/README.md](../backend/README.md) para los endpoints y cómo
correrlas). El frontend cubre las 24 historias sobre esos endpoints (ver
[frontend/README.md](../frontend/README.md)).

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

Decisiones tomadas al cerrar HU-03:

- `Activo` y `FuenteIngreso` tienen `periodo_fiscal_id` obligatorio. El
  patrimonio, la conciliación y el resumen de un año usan solo los
  registros de ese año (antes mezclaban todos los años).
- El `Activo` INVENTARIO que crea un cierre queda en el periodo cerrado,
  así que cada año cuenta solo su propio inventario final; desaparece la
  regla especial de «solo el inventario del último cierre».
- No se pueden registrar activos ni ingresos en un periodo cerrado (409).
- Para no obligar a recrear la base de desarrollo, `database.py` aplica al
  arrancar una migración puntual e idempotente que agrega la columna y
  asigna los registros existentes al periodo más reciente de su
  contribuyente (o al del cierre, para el inventario).

Decisiones sobre la edición y eliminación:

- Activos e ingresos se corrigen o eliminan solo con el periodo abierto,
  igual que se registran. El año de un registro no se edita: si quedó en
  el año equivocado, se elimina y se vuelve a registrar.
- Un contribuyente solo se elimina si no tiene años gravables ni
  inventario: borrar en cascada su información tributaria con un clic es
  demasiado riesgoso; la eliminación es para registros hechos por error.

Decisiones del incremento 6 (seguridad):

- El bloqueo es por email, no por IP, y aplica también a emails
  inexistentes: así el 429 no revela qué cuentas existen. Los intentos
  hechos durante el bloqueo se registran pero no lo extienden, para que un
  atacante insistiendo no deje por fuera indefinidamente al contador.
- La auditoría se registra en un middleware a partir del nombre del
  endpoint, en vez de que cada servicio la llame. Una prueba falla si se
  agrega un endpoint que modifica datos sin declararlo como auditable.
- Las descargas de reportes también se auditan: son salida de información
  tributaria de terceros.
- El archivo de exógena se valida por tamaño (5 MB por defecto) y por su
  firma real de Excel, no solo por la extensión.
- Pendiente conocido: el token JWT se guarda en `localStorage`, expuesto si
  la app tuviera una falla XSS. Moverlo a una cookie `HttpOnly` exige
  protección CSRF; se deja documentado.

## Próximos pasos

1. Regenerar `diagrama-clases.png` a partir de
   [07. Diagrama de clases](07-diagrama-clases.md) (el texto ya incluye la
   relación `PeriodoFiscal` → `Activo` / `FuenteIngreso`).
2. Opcional: copiar los activos de un año al siguiente al abrir un periodo,
   para no volver a digitar bienes que se mantienen.
