# 4. Arquitectura del proyecto

## Arquitectura definida

La aplicación es **móvil, para Android e iOS**, por lo que la arquitectura
separa claramente el cliente (app multiplataforma) del servidor (API REST),
comunicándose por HTTP/JSON. Se mantienen las tres capas conceptuales, pero
cada una vive en un proyecto distinto:

![Arquitectura del proyecto](img/arquitectura.png)

### Capa de presentación — App multiplataforma (Kotlin Multiplatform)

Se implementa con **Kotlin Multiplatform (KMP)** y **Compose Multiplatform**
para la interfaz, lo que permite compartir un único código base de Kotlin
entre Android e iOS (en vez de mantener dos apps nativas separadas). La app
consume la API REST del backend y se adapta según el perfil del
contribuyente (`ASALARIADO` vs. `INDEPENDIENTE`/`MIXTO`), mostrando solo las
pantallas que correspondan.

### Capa de lógica de negocio — API REST

Se implementa con **FastAPI** (Python), expuesta como una API REST pura (sin
frontend embebido). Se organiza en **routers** independientes por módulo:
`patrimonio`, `inventario`, `movimientos` y `reportes`, cada uno con sus
propios esquemas de validación (Pydantic) y su lógica de negocio en un
módulo `services.py`.

### Capa de datos

Se implementa con **SQLAlchemy** (ORM) sobre una base de datos **PostgreSQL**,
que almacena las entidades del [modelo de clases](07-diagrama-clases.md):
`Contribuyente`, `Activo`, `FuenteIngreso`, `Producto`, `Movimiento`,
`DocumentoSoporte`, `PeriodoFiscal`, entre otras.

## Stack tecnológico definitivo

| Componente | Tecnología |
|---|---|
| App móvil (Android + iOS) | Kotlin Multiplatform (KMP) |
| Interfaz (UI compartida) | Compose Multiplatform |
| Cliente HTTP (móvil) | Ktor Client (multiplataforma; Retrofit no sirve para iOS) |
| Backend / API | FastAPI (Python 3) |
| Validación de datos (API) | Pydantic |
| ORM | SQLAlchemy |
| Base de datos | PostgreSQL |
| Control de versiones | Git + GitHub |
| Exportación de reportes | `openpyxl` (Excel) y `reportlab` o `WeasyPrint` (PDF), generados por el backend y descargados por la app |

## Por qué este stack

- **Kotlin Multiplatform en vez de Kotlin nativo puro**: Kotlin nativo
  (Activities/Fragments tradicionales) solo compila para Android. Como el
  proyecto debe cubrir **Android e iOS**, KMP permite mantener Kotlin como
  lenguaje —conservando la decisión ya tomada por el equipo— y compartir la
  lógica de negocio, los modelos de datos y las llamadas a la API entre
  ambas plataformas, en vez de escribir (y mantener) dos apps separadas en
  dos lenguajes distintos (Kotlin + Swift).
- **Compose Multiplatform** para la interfaz: permite además compartir la
  UI (no solo la lógica) entre Android e iOS, reduciendo el trabajo de
  diseño duplicado.
- **Ktor Client en vez de Retrofit**: Retrofit es una librería exclusiva de
  Android; en un proyecto KMP el cliente HTTP debe ser multiplataforma, y
  Ktor (del mismo ecosistema de JetBrains/Kotlin) es la opción estándar.
- **FastAPI en vez de Django**: al no necesitar renderizar HTML (la
  interfaz vive en la app), no se requiere un framework "full stack" como
  Django. FastAPI es más liviano, está diseñado específicamente para
  exponer APIs REST, genera documentación interactiva automática
  (Swagger/OpenAPI) que sirve para probar y sustentar los endpoints, y
  sigue siendo Python.
- **PostgreSQL como motor de base de datos**: ofrece un manejo más estricto
  y confiable de tipos numéricos exactos (`NUMERIC`), lo cual es relevante
  en un proyecto que gira en torno a valores monetarios (patrimonio,
  inventario, costos). Es gratuito, de código abierto, y se integra de
  forma directa con FastAPI + SQLAlchemy.

## Comunicación entre capas

1. La app (Android o iOS, desde el mismo código Kotlin Multiplatform) hace
   peticiones HTTP (GET/POST/PUT/DELETE) a los endpoints del backend, usando
   Ktor Client.
2. FastAPI recibe la petición, valida los datos con Pydantic, ejecuta la
   lógica de negocio correspondiente y consulta/actualiza PostgreSQL a través de
   SQLAlchemy.
3. El backend responde en formato JSON; la app lo interpreta (usando
   `kotlinx.serialization`) y actualiza la interfaz compartida.
4. Para los reportes (Excel/PDF), el backend genera el archivo y lo expone
   como una descarga; la app dispara la descarga y/o la comparte desde el
   dispositivo (Android o iOS).

## Principios de diseño

- **Separación total cliente-servidor**: la app no contiene lógica de
  negocio ni acceso directo a la base de datos; todo pasa por la API.
- **Código compartido entre plataformas**: toda la lógica que no dependa de
  una API específica del sistema operativo (modelos, llamadas a la API,
  validaciones de formulario) vive en el módulo común (`commonMain`) de
  KMP, minimizando el código exclusivo de Android o de iOS.
- **Organización por router en el backend**: cada módulo de negocio
  (patrimonio, inventario, movimientos, reportes) es un router
  independiente, siguiendo la organización de carpetas definida en [02.
  Estructura del proyecto](02-estructura-proyecto.md).
- **Trazabilidad**: todo movimiento de inventario queda vinculado a su
  documento soporte y a su periodo fiscal (ver notas del [diagrama de
  clases](07-diagrama-clases.md)).
- **Extensibilidad por perfil**: la API no obliga a un contribuyente
  asalariado a interactuar con los endpoints de inventario; la app los
  oculta condicionalmente según `tipoContribuyente`.
