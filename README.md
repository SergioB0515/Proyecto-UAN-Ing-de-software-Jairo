# Declaración de renta para contadores (Colombia)

Aplicación web para preparar y gestionar declaraciones de renta de personas
naturales (formulario 210): cruce con la exógena de la DIAN, liquidación con
norma por casilla y seguimiento de cada declaración.

Proyecto del curso de Ingeniería de Software, Universidad Antonio Nariño.

## Funciones

| Área | Contenido |
|---|---|
| Cartera | Obligación de declarar, vencimiento por NIT, etapa de cada declaración, alertas. |
| Exógena | Importación del reporte, cuadre de los cinco topes, conciliación por registro, cruce con lo declarado. |
| Liquidación | Cédulas (general como grilla de 4 columnas), topes y límites, impuesto, anticipo, sanción, saldo. Borrador del 210 en PDF y papel de trabajo con fórmula y norma. |
| Gestión | Etapas, documentos del cliente, presentación, corrección, comparativo, firmeza, beneficio de auditoría, intereses de mora, informe para el cliente. |
| Negocio | Inventario con kardex (PEPS y promedio), costo de ventas, depreciación, bancarización, pérdidas, cierre. |

No presenta la declaración ante la DIAN ni reemplaza el criterio del contador.

## Ejecución

```bash
# backend/ (ver backend/README.md)
uvicorn main:app --reload          # http://127.0.0.1:8000
python semilla_demo.py             # datos demo: contador@demo.co / demo1234
pytest

# frontend/
npm install && npm run dev         # http://localhost:5173
```

Con Docker: `docker compose up` (instrucciones en `docker-compose.yml`).

## Estructura

```
backend/        FastAPI. Un módulo por área en backend/modulos/, cada uno con README.
frontend/       Vue 3 + Vite + Tailwind.
documentacion/  Requisitos, arquitectura, diagramas, historias de usuario, evidencias.
```

## Decisiones técnicas

- Dinero en `Decimal`, redondeo explícito.
- Motor de liquidación como función pura: sin base de datos, se prueba sin servidor.
- Parámetros por año (UVT, tabla del art. 241, topes, tasas de mora) con su fuente legal.
- Cada renglón de la liquidación lleva fórmula y norma.
- Aislamiento por contador y registro de auditoría de toda modificación.

## Documentación

| Documento | Contenido |
|---|---|
| [01](documentacion/01-presentacion-proyecto.md) | Presentación y alcance |
| [02](documentacion/02-estructura-proyecto.md) | Estructura |
| [03](documentacion/03-logica-proyecto.md) | Lógica y procesos |
| [04](documentacion/04-arquitectura.md) | Arquitectura y stack |
| [05](documentacion/05-modelo-desarrollo.md) | Modelo de desarrollo |
| [06](documentacion/06-historias-usuario.md) | Historias de usuario |
| [07](documentacion/07-diagrama-clases.md) | Diagrama de clases |
| [08](documentacion/08-diagrama-flujo.md) | Diagrama de flujo |
| [09](documentacion/09-avances-proyecto.md) | Avances |
| [10](documentacion/10-evidencias-funcionamiento.md) | Evidencias |
| [11](documentacion/11-roadmap-tecnico-y-monetizacion.md) | Roadmap técnico y mercado |
| [12](documentacion/12-plan-inmediato.md) | Plan de trabajo inmediato |
| [13](documentacion/13-plan-segunda-iteracion.md) | Plan de trabajo — segunda iteración |

## Stack

Vue 3, Vite, Tailwind · FastAPI, SQLModel · PostgreSQL · JWT, argon2 ·
openpyxl, reportlab · Docker · GitHub Actions.
