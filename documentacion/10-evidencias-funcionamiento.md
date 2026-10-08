# 10. Evidencias de funcionamiento

Capturas de la aplicación completa (backend FastAPI + frontend Vue 3)
corriendo en local, organizadas por historia de usuario (ver
[06. Historias de usuario](06-historias-usuario.md)). Todas salen de un
mismo recorrido de punta a punta, automatizado con Playwright sobre una
base de datos PostgreSQL vacía:

1. Una contadora crea su cuenta y configura los umbrales de 2025.
2. Registra un contribuyente **mixto**, abre el año gravable 2025 y carga
   su patrimonio e ingresos con vínculos DIAN.
3. Importa el archivo de exógena de prueba
   (`backend/tests/fixtures/reporte_exogena_ejemplo.xlsx`, sintético pero
   con la misma estructura del archivo real de la DIAN).
4. Revisa obligación de declarar, conciliación y borrador de renglones.
5. Registra inventario (producto, proveedor, factura, dos compras y una
   venta) e intenta una venta sin existencias suficientes.
6. Cierra el año, descarga reportes y revisa el panel de cartera con un
   segundo contribuyente asalariado sin exógena.

Además del recorrido visual, el backend tiene **152 pruebas automáticas**
contra PostgreSQL real (`cd backend && pytest`), que cubren los criterios
de aceptación de cada historia.

## Incremento 1 — Contador, contribuyentes, patrimonio e ingresos

### HU-01 — Registrar e iniciar sesión como contador
![Inicio de sesión](evidencias/hu01-login.png)

**Resultado:** registro e inicio de sesión con JWT. La sesión sobrevive a
una recarga (se valida con `GET /contadores/yo`) y un token inválido o
vencido devuelve al login.

### HU-02 — Registrar contribuyentes
![Nuevo contribuyente](evidencias/hu02-nuevo-contribuyente.png)

**Resultado:** alta con nombre, NIT, régimen y tipo (asalariado,
independiente o mixto). Cada contador ve solo sus contribuyentes; pedir el
de otro contador responde 404.

### HU-03 y HU-04 — Fuentes de ingreso y activos por periodo
![Patrimonio e ingresos](evidencias/hu03-hu04-patrimonio-ingresos.png)

**Resultado:** cada activo y cada fuente de ingreso queda asociado al año
gravable seleccionado, con su vínculo DIAN opcional (código de concepto o
palabra clave). El patrimonio líquido y el total de ingresos se calculan
por año. Un valor menor o igual a cero se rechaza (422).

## Incremento 2 — Exógena y obligación de declarar

### HU-05, HU-06 y HU-07 — Importar la exógena, consultarla y verificar la obligación
![Exógena importada](evidencias/hu05-hu06-hu07-exogena.png)

**Resultado:** el archivo se importa y la respuesta informa cuántos
registros y topes se leyeron (y qué filas no se pudieron leer, si las hay).
Se ven los topes, la evaluación de los cinco criterios contra los umbrales
en UVT y la tabla de lo reportado por terceros, filtrable por concepto y
NIT. Los registros autorreportados y los de la DIAN quedan marcados.

![Umbrales UVT](evidencias/hu07-umbrales.png)

**Resultado:** los umbrales por año gravable (valor de la UVT y topes en
UVT) se registran o corrigen desde la aplicación; la tabla muestra su
equivalente en pesos.

## Incremento 3 — Conciliación y borrador

### HU-08 — Conciliar lo declarado contra la exógena
![Conciliación](evidencias/hu08-conciliacion.png)

**Resultado:** libro de dos columnas (declarado frente a exógena) con la
diferencia y el estado de cada concepto: el apartamento y la venta
**coinciden**, la cuenta de ahorros tiene una **discrepancia** de
−$500.000, la moto **no tiene reporte de terceros** y el CDT y los impuestos
quedan como **no declarados**. La retención de notaría (concepto 1032) no
se cruza con el ingreso del mismo código.

### HU-09 — Ver solo lo que exige acción
![Filtro de no declarados](evidencias/hu09-conciliacion-no-declarado.png)

**Resultado:** el filtro por estado deja solo los conceptos no declarados y
explica qué significa cada estado.

### HU-10 — Borrador de valores por renglón
![Borrador por renglón](evidencias/hu10-borrador-renglones.png)

**Resultado:** los valores de la exógena agrupados por el renglón del
formulario 210 que sugiere la DIAN, con la advertencia de que son un punto
de partida.

## Incremento 4 — Inventario

### HU-11 — Categorías y productos
![Productos y categorías](evidencias/hu11-productos-categorias.png)

**Resultado:** productos con código, clasificación de IVA, método de
costeo y categoría; se pueden desactivar. La pestaña de inventario no
aparece para contribuyentes asalariados.

### HU-12 — Movimientos de inventario
![Movimientos](evidencias/hu12-movimientos.png)

**Resultado:** compras y ventas con documento soporte obligatorio y fecha
dentro del año gravable. Una venta de 500 unidades con 30 en existencia se
rechaza con el mensaje del backend (409).

### HU-13 — Proveedores y documentos soporte
![Proveedores y documentos](evidencias/hu13-proveedores-documentos.png)

### HU-14 — Kardex y costo de ventas
![Kardex y costo de ventas](evidencias/hu14-kardex-costo-ventas.png)

**Resultado (verificado a mano):** compras de 100 u. a $2.000 y 50 u. a
$2.300; venta de 120 u. por PEPS = 100 × $2.000 + 20 × $2.300 =
**$246.000** de costo de ventas. Quedan 30 u. × $2.300 = **$69.000** de
inventario final.

## Incremento 5 — Cierre, reportes, resumen y cartera

### HU-15 y HU-16 — Cierre de periodo y reportes
![Cierre y reportes](evidencias/hu15-hu16-cierre-reportes.png)

**Resultado:** al cerrar 2025 el inventario final ($69.000) queda como
activo del año. Los cinco reportes se descargan en Excel y PDF (el
recorrido descargó `conciliacion` en PDF y `kardex` en Excel).

![Periodo cerrado](evidencias/hu15-periodo-cerrado.png)

**Resultado:** con el año cerrado los formularios desaparecen y el
inventario del cierre aparece entre los activos: patrimonio de
$131.569.000 = $131.500.000 + $69.000.

### HU-17 — Resumen del contribuyente
![Resumen](evidencias/hu17-resumen.png)

### HU-18 — Panel de cartera
![Cartera](evidencias/hu18-cartera.png)

**Resultado:** ordenado por alertas; el contribuyente sin exógena aparece
al final con el motivo («Aún no se ha importado la exógena de este
periodo»).

![Cartera en móvil](evidencias/movil-cartera.png)

**Resultado:** la interfaz se adapta a pantallas pequeñas; las tablas
anchas se desplazan horizontalmente dentro de su recuadro.

## Incremento 6 — Seguridad y trazabilidad

### HU-19 — Bloqueo por intentos fallidos
![Cuenta bloqueada](evidencias/hu19-bloqueo-intentos.png)

**Resultado:** al sexto intento con contraseñas equivocadas el login
responde 429 y la pantalla indica cuánto esperar. El bloqueo aplica aunque
el email no exista (en la captura, uno inexistente), para no revelar qué
cuentas están registradas.

### HU-19 y HU-20 — Accesos y cambio de contraseña
![Mi cuenta](evidencias/hu19-hu20-mi-cuenta.png)

**Resultado:** el cambio exige la contraseña actual (con una incorrecta
responde «La contraseña actual no es correcta») y la nueva debe cumplir la
política. La tabla muestra los accesos con su IP; si hubo intentos
fallidos desde el último ingreso, se avisa.

### HU-21 — Actividad registrada
![Actividad](evidencias/hu21-actividad.png)

**Resultado:** cada acción que modifica datos y cada reporte descargado
quedan registrados con fecha, contribuyente e IP, sin que el contador haga
nada. Se puede filtrar por contribuyente.

## Incremento 7 — Calidad de vida

### HU-22 — Corregir o eliminar registros
![Editar y eliminar](evidencias/hu22-editar-eliminar.png)

**Resultado:** cada activo e ingreso se edita en el mismo formulario y se
elimina con confirmación en la fila. Con el año cerrado no aparecen las
acciones. Un contribuyente con años gravables no se puede eliminar (la app
explica por qué).

### HU-23 — Copiar los activos del año anterior
![Copiar activos](evidencias/hu23-copiar-activos.png)

**Resultado:** al abrir 2025, «Copiar activos de 2024» trae el apartamento
y la cuenta con su valor y vínculo DIAN; ejecutarlo de nuevo no duplica.

### HU-24 — Declarar desde la conciliación
![Declarar desde la conciliación](evidencias/hu24-declarar-desde-conciliacion.png)

**Resultado:** en la venta reportada por la notaría (no declarada), el
formulario llega con el concepto, los $50.000.000 y el código 1032, y
sugiere «Ingreso» por el detalle. Al registrarlo, la conciliación se
recalcula: pasa de 4 a 3 no declarados y de 0 a 1 coincidencia.

