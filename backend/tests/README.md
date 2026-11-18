# tests/

`pytest` + `TestClient` contra PostgreSQL real (`renta_test_db`). Cada prueba
revierte su transacción. Las de motor, cédula general, cruce y gestión prueban
funciones puras sin servidor.
