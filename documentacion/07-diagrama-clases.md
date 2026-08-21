# 7. Diagrama de clases

El modelo tiene dos niveles: uno general (`Contribuyente`, `FuenteIngreso`,
`Activo`), que aplica a cualquier usuario incluyendo los asalariados, y uno
específico de inventario, que solo aplica cuando el contribuyente tiene
negocio.

![Diagrama de clases](img/diagrama-clases.png)

## Clases — nivel general (todos los usuarios)

| Clase | Responsabilidad |
|---|---|
| `Contribuyente` | Representa a cualquier usuario de la app; define su tipo (asalariado, independiente o mixto) y su régimen tributario. |
| `FuenteIngreso` | Registra cada ingreso del contribuyente (salario, honorarios, ventas, arriendos) con su respectiva retención en la fuente. |
| `Activo` | Registra cada bien que compone el patrimonio del contribuyente (cuenta bancaria, vehículo, inmueble, inversión), independientemente de si tiene negocio o no. |

## Clases — módulo de inventario (solo negocios)

| Clase | Responsabilidad |
|---|---|
| `Categoria` | Agrupa los productos según su naturaleza (ej. materia prima, producto terminado). |
| `Producto` | Unidad central del inventario; pertenece a un `Contribuyente` y define su clasificación fiscal y método de costeo aplicable. |
| `MetodoCosteo` | Enumeración con los métodos aceptados fiscalmente (PEPS, promedio ponderado). |
| `Proveedor` | Tercero del cual se originan los movimientos de compra. |
| `Movimiento` | Registra cada entrada o salida de inventario, con cantidad, valor y fecha. |
| `DocumentoSoporte` | Representa la factura, acta o nota que respalda un movimiento, para efectos de trazabilidad y auditoría. |
| `PeriodoFiscal` | Agrupa los movimientos correspondientes a un año gravable, necesario para el cierre y los reportes de renta. |

## Relaciones principales

- Un `Contribuyente` tiene muchas `FuenteIngreso` y muchos `Activo`
  (composición 1 — \*); esta relación aplica a todos los usuarios.
- Un `Contribuyente` tiene muchos `Producto` (1 — \*) **solo** si su
  `tipoContribuyente` es independiente o mixto; los asalariados no generan
  esta relación.
- Una `Categoria` puede agrupar muchos `Producto` (**agregación**, 1 — \*):
  si se elimina o reclasifica una categoría, los productos no dejan de
  existir.
- Cada `Producto` usa un `MetodoCosteo` (\* — 1) y tiene muchos `Movimiento`
  (1 — \*).
- Un `Proveedor` puede originar muchos `Movimiento` de compra (1 — \*).
- Cada `Movimiento` está respaldado por un `DocumentoSoporte` (\* — 1) y
  pertenece a un `PeriodoFiscal` (\* — 1).

## Notas del modelo

- `Movimiento.valorTotal` es un **atributo derivado**
  (`cantidad × valorUnitario`); no se almacena de forma independiente, para
  evitar inconsistencias si se edita uno de los dos valores base.
- Cada movimiento queda vinculado a un documento soporte y a un periodo
  fiscal, garantizando trazabilidad y cumplimiento tributario ante la DIAN.
