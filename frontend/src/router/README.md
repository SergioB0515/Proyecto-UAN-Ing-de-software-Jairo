# src/router/

Rutas de la SPA (`vue-router`). El *guard* manda al login si no hay token y,
al recargar la página, reconstruye la sesión con `GET /contadores/yo`. Las
pantallas de un contribuyente son rutas hijas de `/contribuyentes/:id` y el
año gravable viaja en la query (`?periodo=ID`).
