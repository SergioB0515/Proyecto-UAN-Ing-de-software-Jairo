# modulos/conciliacion/

Motor de conciliación entre lo importado de la DIAN (`RegistroExogena`) y
lo registrado por el contador (`FuenteIngreso`, `Activo`), más el borrador
de valores sugeridos por renglón. No tiene modelo de datos propio: ambos
resultados se calculan al momento de la consulta, siempre sobre el
`ReporteExogena` más reciente del periodo. Ver Procesos 6 y 7 en
[03. Lógica del proyecto](../../../documentacion/03-logica-proyecto.md) y
HU-08 a HU-10.

- El cruce usa el vínculo DIAN de cada ítem: primero código de concepto,
  luego palabra clave en el detalle. Entre varios candidatos se elige el
  de valor más cercano.
- Tolerancia de `COINCIDE`: la mayor entre $1.000 y el 0,5 % del valor
  reportado.
- Quedan fuera del cruce las filas autoreportadas, las reportadas por la
  propia DIAN y las de retención (ver la nota sobre el concepto 1032 en
  [09. Avances del proyecto](../../../documentacion/09-avances-proyecto.md)).
  Los consumos con tarjeta (1023) no generan alerta `NO_DECLARADO`.
- `resumen` cuenta los ítems por estado; `NO_DECLARADO` es el número de
  alertas que usará el panel de cartera (HU-18).

## Cruce con la DIAN (`cruce.py`)

`GET /contribuyentes/{id}/periodos-fiscales/{pid}/cruce-dian` compara el
borrador de liquidación con la exógena. Son funciones puras; responden tres
preguntas:

1. **¿El archivo es coherente consigo mismo?** Cada uno de los cinco topes se
   reconstruye desde su detalle. El de patrimonio es el mayor entre lo reportado
   por terceros y lo declarado el año anterior, y los bienes en copropiedad
   cuentan por su porcentaje de participación.
2. **¿Lo que se va a declarar aguanta el cruce?** Patrimonio (casilla 29),
   ingresos brutos, ganancias ocasionales (112), retenciones (132) y saldo a
   favor anterior (131) frente a lo reportado.
3. **¿Se está dejando plata sobre la mesa?** Retenciones reportadas que no se
   restan y compras con factura electrónica sin registrar para el 1 %.

| Severidad | Qué significa |
|---|---|
| `ALTA` | Se declara menos de lo que un tercero reportó: origina requerimiento |
| `MEDIA` | Hay que poder explicarlo (menos patrimonio que el año anterior, retenciones sin respaldo en la exógena, gastar o mover más de lo que se declara ganar) |
| `OPORTUNIDAD` | El contribuyente tiene derecho a algo que no está tomando |
| `OK` / `SIN_DATO` | Cubre lo reportado / la exógena no trae el dato |

Los consumos con tarjeta, las compras y los movimientos de cuentas ya no salen
como «no declarados» en la conciliación registro por registro: son flujos, no
bienes ni ingresos. Las inversiones (un CDT) sí se conservan.

La exógena no es completa ni infalible: una diferencia es una pregunta que hay
que poder responder, no necesariamente un error.
