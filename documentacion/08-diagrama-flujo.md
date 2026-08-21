# 8. Diagrama de flujo

El flujo comienza igual para todos los usuarios y luego se ramifica según el
tipo de contribuyente.

![Diagrama de flujo](img/diagrama-flujo.png)

## Paso común a todos los usuarios

1. **Registrar contribuyente**: el usuario indica si es asalariado,
   independiente o mixto, y su régimen tributario.
2. **Registrar patrimonio general**: el usuario carga sus `Activo` (cuentas,
   vehículo, inmueble, inversiones) y sus `FuenteIngreso` (salario,
   honorarios, arriendos).

## Ruta A — Usuario asalariado (sin negocio)

3. Con la información de patrimonio e ingresos ya registrada, la aplicación
   calcula el **patrimonio líquido** y deja lista la información de soporte
   para la declaración.
4. El usuario **exporta un resumen** de patrimonio e ingresos en Excel o
   PDF, como apoyo directo para diligenciar el formulario de renta.

## Ruta B — Usuario con negocio (independiente o mixto)

3. **Registro de catálogo**: se cargan las categorías y productos, con su
   clasificación fiscal (gravado, exento, excluido).
4. **Registro de movimientos**: cada compra o venta se registra como un
   movimiento, adjuntando el documento soporte correspondiente (factura,
   acta, nota).
5. **Cálculo automático**: la aplicación calcula el saldo de inventario y el
   costo de ventas según el método de costeo configurado.
6. **Cierre de periodo fiscal**: al finalizar el año gravable (31 de
   diciembre), el usuario ejecuta el cierre, que consolida los movimientos
   del periodo y suma el valor del inventario a su patrimonio (`Activo` tipo
   inventario).
7. **Generación de reportes**: la aplicación exporta el kardex, el saldo
   final de inventario y los insumos necesarios para la conciliación fiscal
   (formato 2517), además del resumen de patrimonio e ingresos.

## Convergencia

En ambas rutas, el resultado final es el mismo: un conjunto de reportes que
el usuario utiliza como respaldo al momento de presentar la declaración de
renta ante la DIAN.
