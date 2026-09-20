# src/router/

Rutas de la SPA (`vue-router`), con un *guard* de navegación que redirige a
`LoginView` si no hay token JWT válido en memoria, y que reconstruye la
sesión a partir del contador autenticado al recargar la página.
