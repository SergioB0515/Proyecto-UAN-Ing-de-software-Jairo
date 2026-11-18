# modulos/conciliacion/

Conciliación entre la exógena (`RegistroExogena`) y lo registrado (`FuenteIngreso`,
`Activo`, `VentaInmueble`), borrador por renglón y cruce con la DIAN. Sin tablas
propias: se calcula sobre el `ReporteExogena` más reciente. HU-08 a HU-10.

## Conciliación por registro

- Emparejamiento por código de concepto y luego palabra clave; entre varios
  candidatos, el de valor más cercano.
- `COINCIDE`: diferencia <= max($1.000, 0,5 % del valor reportado).
- Excluidos: autoreportados, reportados por la DIAN y retenciones.
- Tarjeta, compras y movimientos de cuentas son flujos: no generan `NO_DECLARADO`.
  Las inversiones sí se buscan.
- Renglones condicionales de la DIAN: se apartan para que los asigne el contador.

## Cruce con la DIAN (`cruce.py`)

`GET /contribuyentes/{id}/periodos-fiscales/{pid}/cruce-dian`. Funciones puras.

1. Cuadre: cada tope se reconstruye desde el detalle. Tope 2 = max(terceros,
   patrimonio declarado el año anterior). Copropiedad por participación.
2. Riesgo: patrimonio (29), ingresos brutos, GO (112), retenciones (132),
   saldo a favor anterior (131).
3. Oportunidad: retenciones sin restar, compras con factura sin el 1 %.

| Severidad | Caso |
|---|---|
| `ALTA` | Declarado menor que lo reportado por un tercero |
| `MEDIA` | Requiere explicación: patrimonio menor que el año anterior, retenciones sin respaldo, gastos o movimientos superiores a los ingresos |
| `OPORTUNIDAD` | Beneficio no tomado |
| `OK` / `SIN_DATO` | Cubierto / sin dato en la exógena |

Tolerancia de $1.000 (art. 577).
