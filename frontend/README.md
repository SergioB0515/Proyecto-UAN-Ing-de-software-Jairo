# Frontend

Vue 3 (`<script setup>`) + Vite + Tailwind + Axios. Sin lógica de negocio:
todo cálculo lo hace el [backend](../backend/README.md).

## Puesta en marcha

Requisitos: Node.js 18 o superior y el backend corriendo.

```bash
cd frontend
npm install
cp .env.example .env   # opcional: solo si el backend no está en http://127.0.0.1:8000
npm run dev
```

`http://localhost:5173`, permitido en `ORIGENES_PERMITIDOS` del backend.
`npm run build` genera `dist/`.

## Organización

| Ruta | Contenido |
|---|---|
| `src/api/` | `cliente.js` (Axios con el token y redirección al login ante un 401, y `mensajeDeError` para traducir errores de FastAPI) y un módulo por dominio. Las vistas nunca arman URLs. |
| `src/sesion.js` | Token en `localStorage` y contador autenticado. El guard del router reconstruye la sesión con `GET /contadores/yo` al recargar. |
| `src/router/` | Rutas. Las de un contribuyente cuelgan de `/contribuyentes/:id/...` y el año gravable va en `?periodo=ID`, así cada pantalla se puede enlazar o recargar. |
| `src/contexto.js` | `ContribuyenteView` carga el contribuyente y sus periodos una sola vez y los provee (`provide`) a sus pantallas hijas (`useContribuyente()`). |
| `src/views/` | Una vista por pantalla (ver la tabla de abajo). |
| `src/components/` | Piezas reutilizadas: `EstadoConciliacion` (color **y** forma, para no depender solo del color), `TablaObligacion`, `CamposVinculoDian`, `AccionesFila` (editar y eliminar con confirmación en la fila), `DeclararDesdeExogena` y los paneles de inventario. |
| `src/formato.js` | Pesos (COP), cantidades, tamaños de archivo y fechas con formato `es-CO`. |
| `src/soportes.js` | Conteo de soportes por objeto (`useConteoAdjuntos`) y utilidades de adjuntos. |

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
| `UmbralesView` («Parámetros DIAN») + `components/CalendarioVencimientos.vue` | HU-25 |
| `ResumenView` + `components/SeguimientoDeclaracion.vue` | HU-26 |
| `CarteraView` (fecha límite, orden por vencimiento, Descargar Excel/PDF) | HU-25, HU-27 |
| `SoportesView` + `components/PanelAdjuntos.vue` | — |
| `LiquidacionView` + `components/liquidacion/` | Liquidación y borrador del 210 |
| `GestionView` + `components/gestion/` | Gestión de la declaración |

## Diseño

Tokens en `tailwind.config.js`; clases de componente (`.boton`, `.campo`, `.hoja`)
en `src/style.css`. Public Sans con cifras tabulares (`.cifra`). Cada estado de
conciliación tiene color y forma.
