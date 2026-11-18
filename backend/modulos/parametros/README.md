# modulos/parametros/

Parámetros por año gravable. HU-07, HU-25.

- `tablas_oficiales.py`: UVT, tabla del art. 241, límites y topes, con su norma.
- `reajuste_activos.py`: art. 70 y tabla del art. 73 (Decreto 0449 de 2026 para AG 2025).
- `UmbralDeclaracion`: UVT y topes para declarar. `POST /parametros/umbrales/oficiales/{anio}`
  los carga desde la tabla oficial; `POST /parametros/umbrales` los sobrescribe.
- `PlazoDeclaracion`: calendario de vencimientos por último dígito del NIT.
