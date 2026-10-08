# src/api/

`cliente.js` es el único lugar que conoce la URL del backend
(`VITE_API_URL`) y el token JWT: lo agrega a cada petición y, si el backend
responde 401, cierra la sesión y lleva al login. `mensajeDeError(error)`
convierte cualquier error (incluidos los 422 de validación de FastAPI) en
un texto para mostrar.

Cada dominio tiene su módulo (`contribuyentes.js`, `exogena.js`,
`conciliacion.js`, `inventario.js`, `reportes.js`, `parametros.js`,
`cartera.js`), con funciones ya resueltas (`listarActivos(cid, pid)`,
`importarExogena(cid, pid, archivo)`…). Las vistas solo llaman a estas
funciones.
