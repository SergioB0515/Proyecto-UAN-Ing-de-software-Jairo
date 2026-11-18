# modulos/liquidacion/

Liquida renta y complementarios de una persona natural residente y produce el
borrador del formulario 210, con fórmula y norma por renglón.

## Archivos

| Archivo | Contenido |
|---|---|
| `motor.py` | Cálculo. Funciones puras en `Decimal`, sin base de datos ni reloj. |
| `cedula_general.py` | Grilla de 4 columnas de la cédula general y límite del art. 336 num. 3. |
| `calculos_empresariales.py` | Depreciación (arts. 128-137), bancarización (771-5), pérdidas (147, 330), comparación patrimonial (236-239). |
| `venta_inmuebles.py` | Costo fiscal, utilidad y tratamiento de la venta de inmuebles. |
| `sanciones.py` | Extemporaneidad (arts. 639-641). |
| `formulario_210.py` | Casillas oficiales por año gravable. |
| `borrador_210.py` | Borrador del 210 en PDF. |
| `plantillas.py` | Catálogo de deducciones frecuentes con norma y tope. |
| `clasificador.py` | Sugerencia de cédula por palabras del concepto. |
| `modelos.py`, `servicios.py`, `router.py` | Persistencia, armado de insumos (float -> Decimal) y API. |
| `../parametros/tablas_oficiales.py` | Parámetros por año con fuente legal. |

## Orden de `liquidar()`

Patrimonio → depreciación → cédula general → bancarización → topes propios →
deducciones fuera del límite → grilla → compensación de pérdidas → casilla 140
→ pensiones → dividendos → ganancias ocasionales → base y tabla del art. 241 →
comparación patrimonial → descuentos → retenciones → anticipo (art. 807) → saldo.

`servicios.liquidar_periodo()` liquida, calcula la sanción y vuelve a liquidar
con ella (casilla 135).

## Reglas del instructivo del 210 (AG 2024)

| Regla | Dónde |
|---|---|
| Cupo del art. 336 num. 3 en cascada: trabajo, sin vínculo, capital, no laborales | `_repartir_en_cascada` |
| Ninguna columna resta más que su renta líquida | `_repartir_en_cascada` |
| Base del 40 % sin restar devoluciones (casilla 75) | `depurar` |
| Exentas sin límite, sumadas sobre el 40 % | `depurar` |
| Dependientes (139) topados en 42 + 57 | `depurar` |
| 1 % de compras (28) sin generar pérdida | `depurar` |
| Compensación después del límite (87 → 89 → 90) | `liquidar` |
| Descuentos (125) topados en el impuesto de renta (121) | `liquidar` |
| Casilla 140 si 45 > 60 % de 43 | `liquidar` |
| 111 = max(97, 98) + 103 + 107 + 108 − 118 | `liquidar` |

## Lo que decide el contador

- Cédula de cada ingreso. Lo no clasificado se excluye y se reporta.
- Columna de cada deducción (si no la fija, se imputa en orden del formulario).
- Aceptar la renta por comparación patrimonial (art. 236 admite prueba en contrario).
- Operaciones en efectivo > 100 UVT: se listan, no se descuentan.
- Destinación de la venta de vivienda a AFC o crédito (art. 311-1).

## Fuera de alcance

- Presentar la declaración.
- Años sin parámetros: `AnioGravableNoSoportadoError` (422).
- Casillas 94, 95, 104-106, 109, 110, 119, 120, 122, 123, 128: se imprimen
  vacías y señaladas.
- Sanción posterior a emplazamiento (art. 642).

## Venta de inmuebles

- ≥ 2 años: ganancia ocasional (art. 300), casillas 112-115. < 2 años: no laborales.
- Costo fiscal: max(art. 73 reajustado + mejoras, avalúo del año anterior art. 72).
  Tabla AG 2025: Decreto 0449 de 2026. Año sin tabla: factor manual.
- Vivienda: 5.000 UVT exentas (art. 311-1), por participación (Concepto DIAN 6970/2024).
- Retención de la notaría a la casilla 132. Conciliación con el concepto 1032
  como enajenante.

## Numeración

Res. DIAN 000044 de 2024 (AG 2023 en adelante), compilada en la 000227 de 2025.
Válida para AG 2023-2025.

La responsabilidad de la declaración es del contribuyente y del contador que la
firma (art. 581 ET).
