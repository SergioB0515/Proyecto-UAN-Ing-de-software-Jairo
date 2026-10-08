# modulos/auditoria/

Seguridad y trazabilidad (Incremento 6):

- `IntentoAcceso`: cada intento de inicio de sesión (exitoso, fallido o
  bloqueado) con su IP. Con 5 fallos en 15 minutos el email queda bloqueado
  hasta que el fallo más antiguo salga de la ventana (`servicios.py`).
- `EventoAuditoria`: cada acción que modifica datos o descarga un reporte.
  La registra `AuditoriaMiddleware` a partir del nombre del endpoint, sin
  que cada módulo tenga que acordarse de hacerlo.
- `GET /auditoria` y `GET /auditoria/accesos`: lo que ve el contador en la
  pantalla «Actividad». Cada contador solo ve lo suyo.
