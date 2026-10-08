# src/views/

Una vista por pantalla. La tabla vista ↔ historia de usuario está en
[../../README.md](../../README.md). Las vistas hijas de
`ContribuyenteView.vue` obtienen el contribuyente y el periodo seleccionado
con `useContribuyente()` (ver `src/contexto.js`) y se vuelven a montar al
cambiar de año.
