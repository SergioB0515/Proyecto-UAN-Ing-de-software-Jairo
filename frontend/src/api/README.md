# src/api/

Toda la comunicación con el backend vive aquí — las vistas no construyen
URLs ni manejan el token JWT directamente.

- Un cliente HTTP base (Axios o `fetch`) con la URL del backend configurada
  por variable de entorno (`VITE_API_URL`).
- Un interceptor que agrega el header `Authorization: Bearer <token>` a
  toda petición, y que redirige a la vista de login si el backend responde
  401.
- Un módulo por dominio (`contribuyentes.js`, `exogena.js`,
  `conciliacion.js`, `inventario.js`, `reportes.js`), cada uno exponiendo
  funciones ya resueltas (`obtenerContribuyentes()`, `importarExogena(...)`)
  en vez de que cada vista arme su propia petición.
