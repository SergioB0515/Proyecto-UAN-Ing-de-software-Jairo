# 6. Historias de usuario

Historias de usuario organizadas por incremento (ver [05. Modelo de
desarrollo](05-modelo-desarrollo.md)), derivadas directamente del [flujo de
uso de la aplicación](08-diagrama-flujo.md).

**Formato**: *Como [rol], quiero [acción], para [beneficio].*

---

## Épica 1 — Registro de contribuyente y patrimonio general (Incremento 1)

### HU-01 — Registrar contribuyente
**Como** usuario nuevo,
**quiero** registrar mis datos básicos (nombre, RUT, tipo de contribuyente y
régimen tributario),
**para** que la aplicación sepa qué módulos habilitarme.

**Criterios de aceptación:**
- El sistema exige seleccionar un `tipoContribuyente` (asalariado,
  independiente o mixto).
- No se puede continuar sin un RUT válido.
- Si el tipo es "asalariado", el módulo de inventario permanece oculto.

### HU-02 — Registrar fuentes de ingreso
**Como** contribuyente (cualquier perfil),
**quiero** registrar mis fuentes de ingreso (salario, honorarios, ventas,
arriendos) con su retención en la fuente,
**para** tener consolidada la información de ingresos del año gravable.

**Criterios de aceptación:**
- Puedo registrar más de una fuente de ingreso.
- Cada fuente queda asociada a un periodo fiscal.
- El sistema valida que el valor anual sea mayor a cero.

### HU-03 — Registrar activos patrimoniales
**Como** contribuyente (cualquier perfil),
**quiero** registrar mis activos (cuentas, vehículos, inmuebles,
inversiones),
**para** que la aplicación calcule mi patrimonio líquido.

**Criterios de aceptación:**
- Puedo clasificar cada activo por tipo (`CUENTA`, `VEHICULO`, `INMUEBLE`,
  `INVERSION`).
- El sistema calcula automáticamente el patrimonio líquido total sumando
  todos mis activos.

### HU-04 — Exportar resumen de patrimonio e ingresos
**Como** contribuyente asalariado,
**quiero** exportar un resumen de mi patrimonio e ingresos en Excel o PDF,
**para** usarlo como apoyo al diligenciar mi declaración de renta.

**Criterios de aceptación:**
- El resumen incluye el detalle de activos, fuentes de ingreso y el
  patrimonio líquido calculado.
- El archivo se puede descargar en formato Excel y en PDF.

---

## Épica 2 — Catálogo de inventario (Incremento 2)

### HU-05 — Crear categorías de productos
**Como** contribuyente con negocio,
**quiero** crear categorías para organizar mi inventario,
**para** clasificar mis productos de forma coherente con mi negocio.

**Criterios de aceptación:**
- Puedo crear, editar y desactivar categorías.
- No se puede eliminar una categoría que tenga productos activos asociados
  (coherente con la relación de **agregación**, no de composición, entre
  `Categoria` y `Producto`).

### HU-06 — Registrar productos
**Como** contribuyente con negocio,
**quiero** registrar mis productos con su clasificación fiscal de IVA y su
método de costeo,
**para** que el sistema calcule correctamente el valor de mi inventario.

**Criterios de aceptación:**
- Cada producto exige una clasificación IVA (`GRAVADO`, `EXENTO`,
  `EXCLUIDO`).
- Cada producto debe tener asignado un `MetodoCosteo` (PEPS o promedio
  ponderado).

---

## Épica 3 — Movimientos de inventario (Incremento 3)

### HU-07 — Registrar entradas de inventario (compras)
**Como** contribuyente con negocio,
**quiero** registrar cada compra de mercancía adjuntando su factura,
**para** mantener actualizado mi stock y contar con el soporte documental.

**Criterios de aceptación:**
- No se puede registrar una entrada sin un `DocumentoSoporte` asociado.
- El stock del producto se actualiza automáticamente al guardar el
  movimiento.

### HU-08 — Registrar salidas de inventario (ventas)
**Como** contribuyente con negocio,
**quiero** registrar cada venta de mercancía,
**para** que el sistema descuente el inventario y calcule el costo de la
venta.

**Criterios de aceptación:**
- El sistema valida que haya stock suficiente antes de registrar la salida.
- El `valorTotal` del movimiento se calcula automáticamente (no se ingresa
  manualmente).

### HU-09 — Registrar proveedores
**Como** contribuyente con negocio,
**quiero** registrar mis proveedores,
**para** asociar cada compra con el tercero que la originó.

**Criterios de aceptación:**
- Puedo clasificar al proveedor como persona natural o jurídica.
- El sistema exige un número de identificación único por proveedor.

---

## Épica 4 — Costeo de inventario (Incremento 4)

### HU-10 — Calcular el costo de ventas
**Como** contribuyente con negocio,
**quiero** que el sistema calcule automáticamente el costo de ventas según
el método de costeo de cada producto,
**para** no tener que hacer el cálculo manualmente y evitar errores.

**Criterios de aceptación:**
- Si el método es PEPS, las salidas se costean con las entradas más
  antiguas disponibles.
- Si el método es promedio ponderado, el sistema recalcula el costo
  promedio en cada entrada.

---

## Épica 5 — Cierre y reportes (Incremento 5)

### HU-11 — Cerrar el periodo fiscal
**Como** contribuyente con negocio,
**quiero** cerrar el periodo fiscal al finalizar el año gravable,
**para** consolidar mis movimientos y dejar el inventario listo para
declarar.

**Criterios de aceptación:**
- Al cerrar el periodo, no se pueden registrar más movimientos en él.
- El valor final del inventario se refleja como un activo dentro de mi
  patrimonio.

### HU-12 — Generar reportes de cierre
**Como** contribuyente con negocio,
**quiero** generar el kardex, el saldo de inventario y los insumos del
formato 2517,
**para** contar con el soporte necesario para mi declaración de renta.

**Criterios de aceptación:**
- El kardex muestra el histórico de movimientos por producto.
- Los reportes se pueden exportar en Excel y en PDF.

### HU-13 — Ver reportes consolidados (ambos perfiles)
**Como** cualquier contribuyente,
**quiero** ver en un solo lugar el resumen de mi patrimonio, mis ingresos y
(si aplica) mi inventario,
**para** tener toda la información lista antes de presentar mi declaración.

**Criterios de aceptación:**
- La vista de reportes se adapta según `tipoContribuyente`: un asalariado no
  ve secciones de inventario.
- El resumen indica claramente qué periodo fiscal corresponde a la
  información mostrada.
