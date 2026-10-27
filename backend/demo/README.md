# Datos de demostración y guion de la demo

Todo lo de esta carpeta existe para una sola cosa: que mostrar la aplicación
no dependa de registrar datos a mano ni de que nada falle en vivo.

## Cargar los datos

Desde `backend/`, con el entorno virtual activo y `.env` configurado:

```bash
python semilla_demo.py              # carga los datos (no duplica si ya existen)
python semilla_demo.py --reiniciar  # borra los datos demo y los vuelve a crear
python semilla_demo.py --estado     # dice si hay datos cargados
python demo/generar_exogena_demo.py # genera los Excel para cargar en vivo
```

**Credenciales:** `contador@demo.co` / `demo1234`

La semilla solo toca el contador demo: si ya tienes tu propio usuario con
datos en esa base, no se borra nada tuyo.

## Los seis contribuyentes

No son relleno. Cada uno existe para enseñar un estado distinto, y juntos
cubren los cuatro resultados posibles de la conciliación y cuatro de los
estados de vencimiento.

| Contribuyente | Qué demuestra | Conciliación | Vencimiento |
|---|---|---|---|
| **Luz Marina Cifuentes Rojas** | Caso limpio. Además tiene periodo 2024 con activos, para «copiar activos de otro año» | 3 COINCIDE | Presentada |
| **Héctor Fabio Quintero Pardo** | Diferencia de $80.000 que **no** se marca como error (está en la tolerancia del 0,5 %), y un vehículo que ningún tercero reportó | 2 COINCIDE, 1 no reportado por tercero | Pendiente |
| **Diana Carolina Mosquera Luna** | **El caso que justifica el proyecto**: $42.300.000 de honorarios reportados por un tercero que nunca se declararon, más una discrepancia real de $7.500.000 | 1 COINCIDE, 1 discrepancia, 1 **no declarado** | Próxima a vencer |
| **Jorge Enrique Lamprea Ávila** | Todos los topes por debajo del umbral: el sistema dice «no obligado a declarar» y el contador se ahorra el trabajo | 2 COINCIDE | Pendiente |
| **Nelson Andrés Beltrán Gómez** | Comerciante con inventario: 4 productos, los dos métodos de costeo, kardex y costo de ventas. Obligado, con alerta y sin presentar | 2 COINCIDE, 1 discrepancia, 1 **no declarado**, 2 no reportados | **Vencida** |
| **Sandra Milena Osorio Peña** | Periodo abierto **sin exógena**: es el que se usa para cargar el archivo en vivo | — | Pendiente |

El panel de cartera queda así: 6 contribuyentes, 4 obligados, 2 alertas sin
declarar, 1 vencida, 1 próxima.

### Sobre las fechas de vencimiento

El calendario oficial del año gravable 2025 termina el 26 de octubre de 2026.
Después de esa fecha, cualquier contribuyente sin fecha manual aparece como
**vencida**, y el panel se vería todo en rojo. Por eso cuatro de los seis
llevan `fecha_vencimiento_manual` calculada al momento de sembrar
(hoy + 7, + 21, + 45 y + 60 días): así el panel muestra varios estados sea
cual sea el día de la presentación.

## Archivos de exógena para cargar en vivo

`python demo/generar_exogena_demo.py` deja en `demo/archivos/`:

- **`exogena_osorio_pena_2025.xlsx`** — archivo válido de Sandra Milena. Al
  cargarlo, la conciliación produce de una vez un COINCIDE, una DISCREPANCIA
  (cuenta: declaró $11.300.000, el banco reportó $14.850.000), un NO DECLARADO
  (arriendos por $9.600.000) y un NO REPORTADO POR TERCERO (el carro).
- **`exogena_con_filas_invalidas.xlsx`** — el mismo archivo con dos filas sin
  valor numérico. El importador las reporta como errores de fila y procesa el
  resto, en vez de caerse.
- **`no_es_un_excel.txt`** — para mostrar que la app rechaza lo que no es un
  Excel de la DIAN.

**Descárgalos antes de la presentación.** No dependas de encontrarlos en el
escritorio ni de generarlos en el momento.

## Soportes adjuntos

La semilla crea cuatro soportes y **genera los archivos**, no los sube a mano:

| Adjunto | Va en | Para qué |
|---|---|---|
| `impuesto-predial-2025.pdf` | Activo «Apartamento Suba» de Luz Marina | Recibo que respalda el avalúo |
| `certificado-ingresos-y-retenciones.pdf` | Honorarios de Diana Carolina | Dice $61.500.000; ella declaró $54.000.000. Es el soporte de la discrepancia |
| `rut-actualizado.pdf` | Nelson Andrés (documentos generales) | — |
| `factura-fe-1042.png` | Documento soporte FE-1042 de Nelson | Imagen, para la vista previa |

Los cuatro son previsualizables desde la aplicación.

Se generan así, y no subiéndolos, por el despliegue: los adjuntos viven en
disco y en una plataforma sin disco persistente (Render Free) se borran en
cada reinicio. `asegurar_adjuntos_demo()` los vuelve a crear en cada arranque
si faltan, de modo que la pantalla de Soportes nunca aparece vacía.
`python semilla_demo.py --estado` dice cuántos faltan en disco.

## Guion sugerido (8–10 minutos)

1. **Login** con las credenciales demo. Panel de cartera: seis clientes, dos
   con alertas, uno vencido. *«Esto es lo que un contador no puede ver hoy sin
   abrir cliente por cliente.»*
2. **Jorge Enrique** → obligación de declarar: no supera ningún tope. El
   sistema descarta un cliente en dos segundos.
3. **Diana Carolina** → conciliación. Aquí está el hallazgo: $42.300.000 que
   un tercero reportó y nunca se declararon. Y la discrepancia de $7.500.000.
4. **Héctor Fabio** → la diferencia de $80.000 aparece como COINCIDE. *«No
   genera ruido por cualquier peso de diferencia.»*
5. **Diana Carolina → borrador de renglones**: los valores agrupados por
   renglón del formulario, listos para trasladar.
6. **Nelson Andrés** → inventario, kardex y costo de ventas; cierre del
   periodo en vivo (el periodo queda abierto a propósito).
7. **Diana Carolina → soportes**: el certificado del pagador dice
   $61.500.000 y en la aplicación hay $54.000.000. El hallazgo con su
   respaldo documental al lado.
8. **Sandra Milena → exógena**: cargar `exogena_osorio_pena_2025.xlsx` en
   vivo y pasar de inmediato a la conciliación. Si sobra tiempo, cargar
   `no_es_un_excel.txt` para mostrar la validación.
9. **Exportar** el panel de cartera a Excel o PDF.

## Si algo se daña a mitad de la demo

Con `DEMO_RESET_TOKEN` definido en el entorno, la aplicación expone:

```bash
curl -X POST https://TU-DOMINIO/api/demo/reiniciar -H "X-Demo-Token: TU-TOKEN"
```

Devuelve los datos demo a su estado inicial en segundos, sin abrir una
terminal en el servidor y sin tocar ningún otro usuario. Si la variable no
está definida, el endpoint no existe.

## Sobre las cifras

Las cédulas, NIT, nombres, matrículas y placas son **ficticios**.

Los umbrales UVT (`UMBRALES` en `semilla_demo.py`) y los códigos de concepto
de la exógena son valores de referencia para la demostración: antes de
presentarlos como dato real hay que contrastarlos con la resolución de la
DIAN del año gravable correspondiente.

El año gravable está fijo en `ANIO = 2025`. **No lo derives de la fecha
actual**: si cambia, los cálculos dejan de ser reproducibles y la demo deja
de coincidir con las capturas de `documentacion/10-evidencias-funcionamiento.md`.
