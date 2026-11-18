# App de apoyo a la declaración de renta para contadores (Colombia)

Aplicación web para que un **contador** prepare y gestione las declaraciones
de renta de su cartera de personas naturales: concilia la información exógena
de la DIAN contra lo que va a declarar, liquida el formulario 210 con cada
casilla trazada a su norma y lleva el proceso de cada declaración, desde pedir
los documentos hasta el pago.

Proyecto del curso de Ingeniería de Software (sexto semestre), Universidad
Antonio Nariño.

## Qué hace

| Área | Qué resuelve |
|---|---|
| **Cartera** | Todos los clientes en una tabla: quién está obligado a declarar, cuándo vence según su NIT, en qué etapa va su declaración y quién tiene ingresos o bienes sin declarar. |
| **Exógena y cruce con la DIAN** | Importa el reporte de la DIAN, reconstruye sus cinco topes desde el detalle, concilia registro por registro y compara lo que se va a declarar con lo que reportaron los terceros. |
| **Liquidación y formulario 210** | Depura las cédulas (la general como la grilla de cuatro columnas del 210), aplica topes y límites, calcula impuesto, anticipo, sanción y saldo. Genera el borrador del 210 casilla por casilla y un papel de trabajo con la fórmula y la norma de cada renglón. |
| **Gestión de la declaración** | Etapas del proceso, documentos a pedirle al cliente, registro de lo presentado, correcciones, comparativo con el año anterior, firmeza, beneficio de auditoría, intereses de mora e informe en PDF para el cliente. |
| **Contribuyentes con negocio** | Inventario con kardex (promedio ponderado y PEPS), costo de ventas, depreciación, bancarización, pérdidas fiscales y cierre del periodo. |

Lo que **no** hace: no presenta la declaración (eso solo se hace en los
servicios en línea de la DIAN) ni reemplaza el criterio del contador que la
firma. Cada módulo documenta en su README lo que no cubre.

## Cómo correrlo

1. Backend: ver [backend/README.md](backend/README.md) (PostgreSQL, `.env`,
   `uvicorn main:app --reload`). Queda en `http://127.0.0.1:8000`.
2. Frontend: ver [frontend/README.md](frontend/README.md). Desde la carpeta
   `frontend/`: `npm install` y `npm run dev`. Queda en `http://localhost:5173`.
3. Datos de demostración: desde `backend/`, `python semilla_demo.py`. Entra con
   `contador@demo.co` / `demo1234`. El recorrido está en
   [backend/demo/README.md](backend/demo/README.md).

Pruebas del backend, desde `backend/`: `pytest`. Corren también en GitHub
Actions con cada cambio.

Con Docker, la app completa con su base de datos: ver las instrucciones al
inicio de [docker-compose.yml](docker-compose.yml). La demo pública se despliega
en Render con [render.yaml](render.yaml).

## Estructura

```
backend/        API en FastAPI. Un módulo por área en backend/modulos/,
                cada uno con su README.
frontend/       SPA en Vue 3 + Vite + Tailwind.
documentacion/  Documentos del curso: requisitos, arquitectura, diagramas,
                historias de usuario y evidencias.
```

Módulos del backend: `contadores`, `contribuyentes`, `exogena`, `parametros`,
`conciliacion`, `liquidacion`, `gestion`, `inventario`, `movimientos`,
`reportes`, `cartera`, `adjuntos`, `auditoria`.

## Decisiones técnicas que importan

- **Dinero en `Decimal`** con redondeo explícito en el motor de liquidación;
  nunca `float` en un cálculo de impuesto.
- **El motor es una función pura**: recibe los datos y los parámetros del año,
  no consulta la base de datos. Por eso se prueba sin servidor.
- **Parámetros como datos con su fuente**: UVT, tabla del art. 241, topes y
  tasas de mora viven en tablas versionadas por año, cada valor con la norma o
  la publicación de donde sale.
- **Cada renglón de la liquidación lleva su fórmula y su norma**: el contador
  puede revisar de dónde sale cada cifra antes de firmar.
- **Multicontador**: cada contador solo ve su cartera, y toda acción que
  modifica datos queda en el registro de actividad.

## Documentación

| Documento | Contenido |
|---|---|
| [01. Presentación del proyecto](documentacion/01-presentacion-proyecto.md) | Descripción general, objetivo y alcance |
| [02. Estructura del proyecto](documentacion/02-estructura-proyecto.md) | Organización de carpetas y módulos |
| [03. Lógica del proyecto](documentacion/03-logica-proyecto.md) | Los procesos que explican el funcionamiento |
| [04. Arquitectura](documentacion/04-arquitectura.md) | Arquitectura y stack tecnológico |
| [05. Modelo de desarrollo](documentacion/05-modelo-desarrollo.md) | Metodología incremental y plan de incrementos |
| [06. Historias de usuario](documentacion/06-historias-usuario.md) | Historias de usuario por épicas |
| [07. Diagrama de clases](documentacion/07-diagrama-clases.md) | Modelo de datos |
| [08. Diagrama de flujo](documentacion/08-diagrama-flujo.md) | Flujo de uso |
| [09. Avances del proyecto](documentacion/09-avances-proyecto.md) | Estado de avance y hallazgos del prototipo |
| [10. Evidencias de funcionamiento](documentacion/10-evidencias-funcionamiento.md) | Capturas de las funcionalidades |
| [11. Roadmap técnico y mercado](documentacion/11-roadmap-tecnico-y-monetizacion.md) | Deuda técnica, siguientes pasos y análisis de mercado |

## Stack

Vue 3 + Vite + Tailwind · FastAPI + SQLModel · PostgreSQL · JWT con `argon2` ·
`openpyxl` y `reportlab` para Excel y PDF · Docker · Render · GitHub Actions.
