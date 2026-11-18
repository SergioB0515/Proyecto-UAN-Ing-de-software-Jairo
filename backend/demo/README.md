# Datos de demostración

```bash
python semilla_demo.py              # carga (idempotente)
python semilla_demo.py --reiniciar  # borra y vuelve a crear
python semilla_demo.py --estado     # informa qué hay cargado
python demo/generar_exogena_demo.py # Excel para cargar en vivo
```

Credenciales: `contador@demo.co` / `demo1234`. Solo se modifica el contador demo.
Datos ficticios. Año gravable fijo: `ANIO = 2025`.

## Contribuyentes

| Contribuyente | Caso | Conciliación | Vencimiento |
|---|---|---|---|
| Luz Marina Cifuentes Rojas | Limpio; periodo 2024 para copiar activos | 3 COINCIDE | Presentada |
| Héctor Fabio Quintero Pardo | $80.000 de diferencia dentro de tolerancia; vehículo no reportado | 2 COINCIDE, 1 no reportado | Pendiente |
| Diana Carolina Mosquera Luna | $42.300.000 de honorarios no declarados; discrepancia de $7.500.000 | 1 COINCIDE, 1 discrepancia, 1 no declarado | Próxima |
| Jorge Enrique Lamprea Ávila | Bajo todos los topes: no obligado | 2 COINCIDE | Pendiente |
| Nelson Andrés Beltrán Gómez | Comerciante: inventario, PEPS y promedio, kardex; periodo abierto | 2 COINCIDE, 1 discrepancia, 1 no declarado, 2 no reportados | Vencida |
| Sandra Milena Osorio Peña | Sin exógena, para cargarla en vivo | — | Pendiente |

Cuatro contribuyentes tienen `fecha_vencimiento_manual` relativa a la fecha de
siembra (+7, +21, +45, +60 días): el calendario oficial del AG 2025 ya venció.

## Gestión

| Contribuyente | Estado |
|---|---|
| Luz Marina | 7 de 7. Declaración 2024 manual: comparativo, coherencias, beneficio negado por el mínimo de 71 UVT. |
| Diana Carolina | Documentos: 2 recibidos, resto pendiente, mensaje para el cliente. |
| Nelson Andrés | Vencido el 20 de agosto: sanción, intereses por mes, aviso de tasa faltante (noviembre 2026). |

## Archivos de exógena (`demo/archivos/`)

- `exogena_osorio_pena_2025.xlsx`: COINCIDE, DISCREPANCIA ($11.300.000 frente a
  $14.850.000), NO_DECLARADO (arriendos $9.600.000), NO_REPORTADO (vehículo).
- `exogena_con_filas_invalidas.xlsx`: dos filas no numéricas, reportadas como error.
- `no_es_un_excel.txt`: rechazado.

## Adjuntos

| Archivo | Asociado a |
|---|---|
| `impuesto-predial-2025.pdf` | Apartamento Suba, Luz Marina |
| `certificado-ingresos-y-retenciones.pdf` | Honorarios de Diana ($61.500.000 frente a $54.000.000 declarados) |
| `rut-actualizado.pdf` | Nelson, documentos generales |
| `factura-fe-1042.png` | Documento FE-1042 de Nelson |

Se generan en código y `asegurar_adjuntos_demo()` los recrea al arrancar si
faltan (disco no persistente).

## Recorrido

1. Cartera: 6 clientes, 4 obligados, 2 alertas, 1 vencido.
2. Jorge Enrique: no obligado.
3. Diana Carolina: conciliación, borrador por renglón, soportes.
4. Héctor Fabio: diferencia dentro de tolerancia.
5. Nelson Andrés: kardex, costo de ventas, cierre del periodo.
6. Sandra Milena: cargar la exógena en vivo.
7. Exportar la cartera.

## Reinicio

Con `DEMO_RESET_TOKEN` definido:

```bash
curl -X POST https://DOMINIO/api/demo/reiniciar -H "X-Demo-Token: TOKEN"
```
