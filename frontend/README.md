# Frontend: SPA de conciliación de renta

Vue 3 (Composition API, `<script setup>`) + Vite + Tailwind CSS + Axios.
Consume la API de [../backend](../backend/README.md); no tiene lógica de
negocio propia: todo cálculo (patrimonio, conciliación, costeo, cierre) lo
hace el backend.

## Puesta en marcha

Requisitos: Node.js 18 o superior y el backend corriendo.

```bash
cd frontend
npm install
cp .env.example .env   # opcional: solo si el backend no está en http://127.0.0.1:8000
npm run dev
```

Abre `http://localhost:5173`. Ese origen ya está permitido en el CORS del
backend (`ORIGENES_PERMITIDOS` en `backend/main.py`); si cambias el puerto,
agrégalo allí.

`npm run build` genera la versión de producción en `dist/`.

## Recorrido mínimo

1. Crea una cuenta de contador.
2. En **Umbrales UVT** registra el año gravable (valor de la UVT y topes);
   sin eso no se puede evaluar la obligación de declarar.
3. En **Contribuyentes** registra uno y abre su año gravable.
4. Carga activos e ingresos (con su código de concepto DIAN o palabra
   clave, para que se crucen) e importa el Excel de exógena. Para probar
   sin un archivo real sirve `backend/tests/fixtures/reporte_exogena_ejemplo.xlsx`.
5. Revisa **Conciliación**, **Borrador por renglón** y **Resumen**; cierra
   el año y descarga reportes en **Cierre y reportes**.

## Organización

| Ruta | Contenido |
|---|---|
| `src/api/` | `cliente.js` (Axios con el token y redirección al login ante un 401, y `mensajeDeError` para traducir errores de FastAPI) y un módulo por dominio. Las vistas nunca arman URLs. |
| `src/sesion.js` | Token en `localStorage` y contador autenticado. El guard del router reconstruye la sesión con `GET /contadores/yo` al recargar. |
| `src/router/` | Rutas. Las de un contribuyente cuelgan de `/contribuyentes/:id/...` y el año gravable va en `?periodo=ID`, así cada pantalla se puede enlazar o recargar. |
| `src/contexto.js` | `ContribuyenteView` carga el contribuyente y sus periodos una sola vez y los provee (`provide`) a sus pantallas hijas (`useContribuyente()`). |
| `src/views/` | Una vista por pantalla (ver la tabla de abajo). |
| `src/components/` | Piezas reutilizadas: `EstadoConciliacion` (color **y** forma, para no depender solo del color), `TablaObligacion`, `CamposVinculoDian`, `AccionesFila` (editar y eliminar con confirmación en la fila), `DeclararDesdeExogena` y los paneles de inventario. |
| `src/formato.js` | Pesos (COP), cantidades y fechas con formato `es-CO`. |

| Vista | Historias |
|---|---|
| `LoginView` | HU-01 |
| `CarteraView` | HU-18 |
| `ContribuyentesView`, `ContribuyenteView` | HU-02 (y apertura de años gravables) |
| `PatrimonioView` | HU-03, HU-04 |
| `ExogenaView` | HU-05, HU-06, HU-07 |
| `UmbralesView` | HU-07 (configuración) |
| `ConciliacionView` | HU-08, HU-09 |
| `BorradorView` | HU-10 |
| `InventarioView` + `components/inventario/` | HU-11 a HU-14 |
| `CierreView` | HU-15, HU-16 |
| `ResumenView` | HU-17 |
| `CuentaView` | HU-19 (accesos), HU-20 |
| `ActividadView` | HU-21 |
| `PatrimonioView`, `ContribuyenteView` (editar y eliminar, copiar activos) | HU-22, HU-23 |
| `ConciliacionView` + `components/DeclararDesdeExogena.vue` | HU-24 |

## Diseño

Tokens en `tailwind.config.js`: tinta `#1E2A36`, papel `#F2F4F0`, verde de
libro contable `#2E6A4F` para acciones y un color por estado de
conciliación (ámbar para discrepancia, rojo para no declarado, pizarra
para sin reporte de terceros). Una sola familia tipográfica (Public Sans)
con cifras tabulares (clase `.cifra`) para que los montos se alineen como
en un libro. Las clases de componente (`.boton`, `.campo`, `.hoja`…) están
en `src/style.css`.

Los textos de la interfaz tutean al contador, igual que los mensajes de
error del backend.
