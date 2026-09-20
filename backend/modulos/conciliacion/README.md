# modulos/conciliacion/

Motor de conciliación entre lo importado de la DIAN (`RegistroExogena`) y
lo registrado por el contador (`FuenteIngreso`, `Activo`), más el borrador
de valores sugeridos por renglón. No tiene modelo de datos propio: ambos
resultados se calculan al momento de la consulta. Ver Procesos 6 y 7 en
[03. Lógica del proyecto](../../../documentacion/03-logica-proyecto.md) y
HU-08 a HU-10.

Excluye del cruce automático las filas autoreportadas, las reportadas por
la propia DIAN, y las de retención asociadas a un ingreso ya cruzado (ver
la nota sobre el concepto 1032 en
[09. Avances del proyecto](../../../documentacion/09-avances-proyecto.md)).
