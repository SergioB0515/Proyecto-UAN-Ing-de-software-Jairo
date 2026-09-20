# modulos/contribuyentes/

CRUD de `Contribuyente`, `Activo` y `FuenteIngreso`; cálculo de patrimonio
líquido. Cada `Activo` y `FuenteIngreso` admite un vínculo DIAN opcional
(código de concepto o palabra clave) usado por el módulo `conciliacion`.
Ver HU-02 a HU-04 en
[06. Historias de usuario](../../../documentacion/06-historias-usuario.md).

Todo endpoint de este módulo filtra por el `contador_id` del token JWT —
un contador nunca puede ver ni modificar contribuyentes de otro contador.
