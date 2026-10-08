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
