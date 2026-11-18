# modulos/auditoria/

- `IntentoAcceso`: cada intento de login con IP. 5 fallos en 15 minutos bloquean el email.
- `EventoAuditoria`: lo registra `AuditoriaMiddleware` según el nombre del endpoint
  (`ACCIONES_AUDITADAS`), solo en respuestas exitosas.
- `GET /auditoria`, `GET /auditoria/accesos`: actividad del propio contador.
