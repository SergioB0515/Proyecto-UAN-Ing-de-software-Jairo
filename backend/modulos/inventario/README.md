# modulos/inventario/

CRUD de `Categoria` y `Producto` (con `MetodoCosteo` y `ClasificacionIva`),
solo habilitado para contribuyentes `INDEPENDIENTE` o `MIXTO` (409 si es
`ASALARIADO`). Ver HU-11 en
[06. Historias de usuario](../../../documentacion/06-historias-usuario.md).

- No se elimina una categoría con productos activos; los inactivos quedan
  sin categoría (agregación).
- Los productos no se borran: se desactivan (`PATCH ... {"activo": false}`).
- El código de producto es único por contribuyente.
- El método de costeo no se puede cambiar si el producto ya tiene
  movimientos (alteraría el costo de ventas ya calculado).
- `stock_actual` lo actualiza solo el módulo `movimientos`.
