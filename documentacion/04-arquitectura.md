# 4. Arquitectura del proyecto

## Arquitectura definida

Arquitectura de **tres capas**, implementada con **Django** (Python) como
framework principal, que cubre tanto el backend como el frontend a través de
sus plantillas (templates), y **MySQL** como motor de base de datos.

![Arquitectura del proyecto](img/arquitectura.png)

### Capa de presentación

Se implementa con **Django Templates** (HTML renderizado del lado del
servidor) y **Bootstrap** para el estilo visual. La interfaz se adapta según
el perfil del contribuyente (`ASALARIADO` vs. `INDEPENDIENTE`/`MIXTO`),
mostrando solo los módulos que correspondan mediante lógica condicional en
las vistas.

### Capa de lógica de negocio

Se implementa con **Django** (`views.py`, `forms.py`, y un módulo
`services.py` por app para la lógica de negocio pura, como el cálculo de
costeo o de patrimonio). El proyecto se organiza en **apps de Django**
independientes por módulo: `patrimonio`, `inventario`, `movimientos` y
`reportes`.

### Capa de datos

Se implementa con el **ORM de Django** sobre una base de datos **MySQL**,
que almacena las entidades del [modelo de clases](07-diagrama-clases.md):
`Contribuyente`, `Activo`, `FuenteIngreso`, `Producto`, `Movimiento`,
`DocumentoSoporte`, `PeriodoFiscal`, entre otras.

## Stack tecnológico definitivo

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3 |
| Framework web (backend + frontend) | Django |
| Frontend / estilos | Django Templates + Bootstrap |
| Base de datos | MySQL |
| ORM | Django ORM |
| Control de versiones | Git + GitHub |
| Exportación de reportes | `openpyxl` (Excel) y `reportlab` o `WeasyPrint` (PDF) |

## Por qué Django + MySQL

- **Un solo lenguaje** (Python) para toda la aplicación: no se requiere
  aprender un framework de JavaScript aparte para el frontend.
- **Django incluye de fábrica**: ORM, sistema de autenticación, panel de
  administración y validación de formularios — herramientas que este
  proyecto necesita (login de contribuyente, CRUD de todas las entidades,
  validaciones de negocio).
- **MySQL** es un motor relacional maduro, ampliamente soportado por
  hosting y por Django out-of-the-box (`mysqlclient` / `django-mysql`), y
  maneja bien las relaciones del modelo de clases (claves foráneas entre
  `Producto`, `Movimiento`, `DocumentoSoporte`, etc.).

## Principios de diseño

- **Separación por app de Django**: cada módulo de negocio (patrimonio,
  inventario, movimientos, reportes) es una app independiente, siguiendo la
  organización de carpetas definida en [02. Estructura del
  proyecto](02-estructura-proyecto.md).
- **Trazabilidad**: todo movimiento de inventario queda vinculado a su
  documento soporte y a su periodo fiscal (ver notas del [diagrama de
  clases](07-diagrama-clases.md)).
- **Extensibilidad por perfil**: la arquitectura no obliga a un
  contribuyente asalariado a interactuar con el módulo de inventario; este
  se activa condicionalmente según `tipoContribuyente`.
