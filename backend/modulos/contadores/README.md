# modulos/contadores/

Registro y autenticación del contador. Ver HU-01 en
[06. Historias de usuario](../../../documentacion/06-historias-usuario.md).

- `modelos.py`: modelo `Contador` (SQLModel).
- `router.py`: endpoints de registro y login (`/contadores/registro`,
  `/contadores/login`).
- `servicios.py`: verificación de credenciales, emisión de JWT.
