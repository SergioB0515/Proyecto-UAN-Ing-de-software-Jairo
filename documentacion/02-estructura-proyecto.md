# 2. Estructura del proyecto

La aplicación se compone de **dos proyectos independientes** que se
comunican por API REST: el backend (FastAPI) y la app móvil multiplataforma
(Kotlin Multiplatform, para Android e iOS). Cada uno vive en su propia
carpeta dentro del repositorio.

```
app_renta_inventario/
│
├── docs/                        # Documentación del proyecto (este contenido)
│   ├── img/                     # Diagramas (clases, flujo, arquitectura)
│   └── *.md
│
├── backend/                     # API REST en FastAPI
│   ├── requirements.txt         # Dependencias (fastapi, uvicorn, sqlalchemy, psycopg2...)
│   ├── main.py                  # Punto de entrada de la aplicación FastAPI
│   ├── database.py              # Conexión SQLAlchemy a PostgreSQL
│   │
│   ├── modulos/
│   │   ├── patrimonio/          # Contribuyente, Activo, FuenteIngreso
│   │   │   ├── models.py        # Modelos SQLAlchemy
│   │   │   ├── schemas.py       # Esquemas Pydantic (validación de entrada/salida)
│   │   │   ├── router.py        # Endpoints (rutas) de este módulo
│   │   │   └── services.py      # Lógica de negocio (cálculo de patrimonio líquido)
│   │   │
│   │   ├── inventario/          # Producto, Categoria, MetodoCosteo
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   └── router.py
│   │   │
│   │   ├── movimientos/         # Movimiento, Proveedor, DocumentoSoporte
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── router.py
│   │   │   └── services.py      # Lógica de negocio (cálculo de costeo PEPS/promedio)
│   │   │
│   │   └── reportes/            # PeriodoFiscal, cierre, exportación
│   │       ├── models.py
│   │       ├── router.py
│   │       └── services.py      # Generación de kardex, exportación Excel/PDF
│   │
│   └── tests/                   # Pruebas del backend
│
└── app-multiplatform/           # App móvil Kotlin Multiplatform (Android + iOS)
    ├── settings.gradle.kts
    │
    ├── shared/                  # Código Kotlin compartido entre Android e iOS
    │   └── src/
    │       ├── commonMain/kotlin/com/uan/rentaapp/
    │       │   ├── data/
    │       │   │   ├── api/         # Cliente Ktor — servicios REST comunes
    │       │   │   └── modelo/      # Data classes (Contribuyente, Activo, Producto...)
    │       │   └── ui/
    │       │       ├── patrimonio/  # Pantallas Compose: contribuyente, activos, ingresos
    │       │       ├── inventario/  # Pantallas Compose: catálogo de productos
    │       │       ├── movimientos/ # Pantallas Compose: entradas/salidas
    │       │       └── reportes/    # Pantallas Compose: cierre y reportes
    │       ├── androidMain/kotlin/  # Código específico de Android (mínimo)
    │       └── iosMain/kotlin/      # Código específico de iOS (mínimo)
    │
    ├── androidApp/               # Punto de entrada Android (usa `shared`)
    │   └── src/main/kotlin/MainActivity.kt
    │
    └── iosApp/                   # Punto de entrada iOS (proyecto Xcode, usa `shared`)
        └── iosApp/iOSApp.swift
```

## Componentes principales

| Componente | Proyecto | Responsabilidad |
|---|---|---|
| `backend/modulos/patrimonio` | Backend | Endpoints CRUD de `Contribuyente`, `Activo`, `FuenteIngreso`; cálculo de patrimonio líquido |
| `backend/modulos/inventario` | Backend | Endpoints CRUD de `Producto`, `Categoria`, `MetodoCosteo` |
| `backend/modulos/movimientos` | Backend | Endpoints de `Movimiento`, `Proveedor`, `DocumentoSoporte`; cálculo de costo de ventas |
| `backend/modulos/reportes` | Backend | Cierre de `PeriodoFiscal`, generación de kardex y exportables |
| `shared/commonMain/.../ui/patrimonio` | App (Android + iOS) | Pantallas compartidas para registrar contribuyente, activos e ingresos |
| `shared/commonMain/.../ui/inventario` | App (Android + iOS) | Pantallas compartidas del catálogo (solo si el contribuyente tiene negocio) |
| `shared/commonMain/.../ui/movimientos` | App (Android + iOS) | Pantallas compartidas de registro de entradas/salidas |
| `shared/commonMain/.../ui/reportes` | App (Android + iOS) | Pantallas compartidas de cierre y descarga de reportes |
| `shared/commonMain/.../data/api` | App (Android + iOS) | Definición de los endpoints que consume la app (Ktor Client) |
| `androidApp/` / `iosApp/` | App | Puntos de entrada específicos de cada plataforma (mínimos, casi todo vive en `shared/`) |

## Criterio de organización

En el **backend**, cada módulo agrupa sus propios modelos, esquemas,
router y servicios, de forma que los incrementos del [modelo de
desarrollo](05-modelo-desarrollo.md) puedan implementarse y probarse de
forma independiente (se puede levantar y probar el módulo de patrimonio sin
que exista todavía el de inventario).

En la **app multiplataforma**, la meta es que la mayor parte del código
—modelos, llamadas a la API, lógica de pantallas— viva en `commonMain/` y
se comparta entre Android e iOS. Solo el código estrictamente dependiente
del sistema operativo (por ejemplo, acceso a almacenamiento específico de
la plataforma) va en `androidMain/` o `iosMain/`.

> **Nota**: esta estructura es la propuesta de organización para cuando
> inicie la implementación. Ver [09. Avances del
> proyecto](09-avances-proyecto.md) para el estado real de desarrollo a la
> fecha.
