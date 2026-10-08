# modulos/contribuyentes/

CRUD de `Contribuyente`, `PeriodoFiscal`, `Activo` y `FuenteIngreso`;
cálculo de patrimonio líquido por año gravable. Cada `Activo` y
`FuenteIngreso` pertenece a un `PeriodoFiscal` (HU-03) y admite un vínculo DIAN opcional
(código de concepto o palabra clave) usado por el módulo `conciliacion`.
Ver HU-02 a HU-04 en
[06. Historias de usuario](../../../documentacion/06-historias-usuario.md).

Todo endpoint de este módulo filtra por el `contador_id` del token JWT —
un contador nunca puede ver ni modificar contribuyentes de otro contador.
