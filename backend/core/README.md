# core/

Código transversal, no específico de ningún módulo de negocio.

- `seguridad.py`: hash de contraseñas (argon2) y creación/verificación de
  tokens JWT.
- `dependencias.py`: dependencia `get_contador_actual`, usada en cada
  router para resolver y validar el contador autenticado a partir del
  token, y para filtrar cualquier consulta por su `contador_id`.
