# App de Patrimonio e Inventario para Declaración de Renta (Colombia)

Aplicación de apoyo a la declaración de renta en Colombia, pensada tanto para
**contribuyentes asalariados** (sin negocio) como para **contribuyentes con
negocio** (comerciantes o independientes que manejan inventario).

## 📌 Estado actual del proyecto

Fase de **diseño y documentación** completada. Implementación pendiente de
inicio (ver [Modelo de desarrollo](docs/05-modelo-desarrollo.md) para el plan
de incrementos).

## 📂 Contenido de la documentación

| Documento | Contenido |
|---|---|
| [01. Presentación del proyecto](docs/01-presentacion-proyecto.md) | Descripción general, objetivo y alcance |
| [02. Estructura del proyecto](docs/02-estructura-proyecto.md) | Organización de carpetas, componentes y módulos propuestos |
| [03. Lógica del proyecto](docs/03-logica-proyecto.md) | Funcionamiento y procesos principales |
| [04. Arquitectura](docs/04-arquitectura.md) | Arquitectura propuesta y stack tecnológico |
| [05. Modelo de desarrollo](docs/05-modelo-desarrollo.md) | Metodología (incremental) y plan de incrementos |
| [06. Historias de usuario](docs/06-historias-usuario.md) | Historias de usuario por perfil e incremento |
| [07. Diagrama de clases](docs/07-diagrama-clases.md) | Modelo de datos del sistema |
| [08. Diagrama de flujo](docs/08-diagrama-flujo.md) | Flujo de uso de la aplicación |
| [09. Avances del proyecto](docs/09-avances-proyecto.md) | Estado de avance a la fecha |
| [10. Evidencias de funcionamiento](docs/10-evidencias-funcionamiento.md) | Evidencias de las funcionalidades implementadas |

## 👤 Perfiles de usuario

- **Asalariado**: registra su patrimonio (cuentas, vehículo, inmueble,
  inversiones) y sus fuentes de ingreso (salario, honorarios).
- **Independiente / mixto**: además de lo anterior, gestiona inventario de
  mercancía (productos, movimientos, costeo, cierre de periodo fiscal).

## 🛠️ Stack definitivo

- **App móvil (Android + iOS)**: Kotlin Multiplatform + Compose Multiplatform + Ktor Client
- **Backend / API**: FastAPI (Python 3) + Pydantic
- **Base de datos**: PostgreSQL + SQLAlchemy (ORM)

Ver el detalle en [04. Arquitectura](docs/04-arquitectura.md).
