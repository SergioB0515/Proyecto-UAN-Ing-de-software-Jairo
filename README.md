# App de Conciliación de Renta para Contadores (Colombia)

Aplicación web pensada para que un **contador** gestione su cartera de
contribuyentes (clientes) y concilie automáticamente la información
exógena de la DIAN contra el patrimonio, los ingresos y (cuando aplique) el
inventario que registra para cada uno — además de verificar si cada uno
está obligado a declarar y armar un borrador de valores por renglón de la
declaración.

## Estado actual del proyecto

**Backend**: los cinco incrementos implementados y probados (114 pruebas
automáticas contra PostgreSQL) — autenticación, contribuyentes y
patrimonio, importación de exógena, obligación de declarar, conciliación,
borrador de renglones, inventario, movimientos y costo de ventas, cierre de
periodo, reportes en Excel/PDF y panel de cartera.
**Frontend**: solo el esqueleto de carpetas. Ver
[backend/README.md](backend/README.md) y
[documentacion/09-avances-proyecto.md](documentacion/09-avances-proyecto.md).

## Contenido de la documentación

| Documento | Contenido |
|---|---|
| [01. Presentación del proyecto](documentacion/01-presentacion-proyecto.md) | Descripción general, objetivo y alcance |
| [02. Estructura del proyecto](documentacion/02-estructura-proyecto.md) | Organización de carpetas, componentes y módulos propuestos |
| [03. Lógica del proyecto](documentacion/03-logica-proyecto.md) | Los once procesos que explican el funcionamiento del sistema |
| [04. Arquitectura](documentacion/04-arquitectura.md) | Arquitectura propuesta y stack tecnológico |
| [05. Modelo de desarrollo](documentacion/05-modelo-desarrollo.md) | Metodología (incremental) y plan de incrementos |
| [06. Historias de usuario](documentacion/06-historias-usuario.md) | 18 historias de usuario en 5 épicas |
| [07. Diagrama de clases](documentacion/07-diagrama-clases.md) | Modelo de datos del sistema |
| [08. Diagrama de flujo](documentacion/08-diagrama-flujo.md) | Flujo de uso de la aplicación |
| [09. Avances del proyecto](documentacion/09-avances-proyecto.md) | Estado de avance y hallazgos del prototipo de validación |
| [10. Evidencias de funcionamiento](documentacion/10-evidencias-funcionamiento.md) | Evidencias de las funcionalidades implementadas |

## Usuario y perfiles

- **Contador**: usuario que se autentica en la aplicación y gestiona su
  cartera de contribuyentes. Es el único rol con inicio de sesión en este
  alcance.
- **Contribuyente**: registro gestionado por un contador. Puede ser
  **asalariado** (patrimonio e ingresos únicamente) o **independiente /
  mixto** (además gestiona inventario de mercancía).

## Lo que hace la aplicación, más allá de señalar diferencias

- **Verifica la obligación de declarar** comparando los topes de la
  exógena contra los umbrales vigentes (UVT) del año gravable.
- **Concilia** lo declarado contra lo reportado por terceros, señalando
  coincidencias, discrepancias y lo que falta por declarar.
- **Arma un borrador por renglón** del formulario de declaración, a partir
  del renglón que la propia DIAN sugiere para cada concepto reportado.
- **Da visibilidad de cartera**: qué contribuyentes están obligados a
  declarar y cuáles tienen alertas pendientes, sin revisarlos uno por uno.

## Stack definitivo

- **Frontend**: Vue 3 (Composition API) + Vite + Tailwind CSS (SPA)
- **Backend / API**: FastAPI (Python 3), rutas síncronas
- **Datos**: SQLModel sobre PostgreSQL
- **Autenticación**: JWT (OAuth2PasswordBearer) + `passlib` con `argon2`
- **Conciliación de información exógena**: `pandas`
- **Exportación de reportes**: `openpyxl` (Excel) y `reportlab` (PDF)

Ver el detalle y las razones de cada elección en
[04. Arquitectura](documentacion/04-arquitectura.md).

## Estructura del repositorio

Ver [02. Estructura del proyecto](documentacion/02-estructura-proyecto.md)
para el árbol completo, incluidos los módulos `parametros` (umbrales de
declaración) y `cartera` (panel consolidado del contador). La carpeta
`backend/` implementa esa estructura completa; `frontend/` aún contiene
solo su esqueleto de carpetas.
