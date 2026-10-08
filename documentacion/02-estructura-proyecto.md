# 2. Estructura del proyecto

La aplicación se compone de **dos proyectos independientes** que se
comunican por API REST (JSON) sobre HTTP: el backend (FastAPI) y el
frontend web (Vue 3 SPA). Cada uno vive en su propia carpeta dentro del
repositorio y se despliega por separado.

```
app_renta_contador/
│
├── documentacion/                # Documentación del proyecto (este contenido)
│
├── backend/                      # API REST en FastAPI
│   ├── requirements.txt          # Dependencias (fastapi, sqlmodel, pandas...)
│   ├── main.py                   # Punto de entrada, registro de routers, CORS
│   ├── database.py               # Engine y sesión SQLModel sobre PostgreSQL
│   │
│   ├── core/
│   │   ├── seguridad.py          # Hash de contraseñas (argon2), emisión/verificación de JWT
│   │   └── dependencias.py       # get_contador_actual (OAuth2PasswordBearer)
│   │
│   ├── modulos/
│   │   ├── contadores/           # Contador: registro, login, perfil
│   │   ├── contribuyentes/       # Contribuyente, Activo, FuenteIngreso; patrimonio líquido
│   │   ├── exogena/               # ReporteExogena, RegistroExogena, catálogo de conceptos DIAN
│   │   ├── parametros/           # Umbrales UVT por año gravable; verificación de obligación de declarar
│   │   ├── conciliacion/         # Motor de conciliación + borrador de renglones sugeridos
│   │   ├── cartera/              # Panel consolidado de todos los contribuyentes del contador
│   │   ├── inventario/           # Producto, Categoria, MetodoCosteo
│   │   ├── movimientos/          # Movimiento, Proveedor, DocumentoSoporte
│   │   ├── reportes/             # PeriodoFiscal, cierre, exportación
│   │   └── auditoria/            # Registro de accesos, bloqueo por intentos fallidos, auditoría de acciones
│   │
│   └── tests/                    # Pruebas del backend (pytest + TestClient)
│
├── .github/workflows/ci.yml      # Integración continua: pruebas del backend y compilación del frontend
│
└── frontend/                     # SPA en Vue 3 + Vite + Tailwind CSS
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js        # Tokens de diseño (colores, tipografía)
    └── src/
        ├── main.js, App.vue      # Arranque y marco (barra lateral)
        ├── sesion.js             # Token JWT y contador autenticado
        ├── contexto.js           # Contribuyente y periodo abiertos, compartidos por sus pantallas
        ├── formato.js            # Pesos, cantidades y fechas en formato colombiano
        ├── api/                  # Cliente Axios (JWT, 401 -> login) y un módulo por dominio
        ├── router/               # Rutas de la SPA y guard de sesión
        ├── views/                # Login, Cartera, Contribuyentes, Umbrales y, por contribuyente:
        │                         # Resumen, Patrimonio, Exógena, Conciliación, Borrador,
        │                         # Inventario, Cierre y reportes
        └── components/           # Estado de conciliación, tabla de obligación, paneles de inventario
```

## Componentes principales

| Componente | Proyecto | Responsabilidad |
|---|---|---|
| `backend/modulos/contadores` | Backend | Registro/login del contador, emisión de JWT |
| `backend/modulos/contribuyentes` | Backend | CRUD de `Contribuyente`, `Activo`, `FuenteIngreso`; cálculo de patrimonio líquido |
| `backend/modulos/exogena` | Backend | Carga del archivo Excel de la DIAN; parseo y normalización a `RegistroExogena`; catálogo de referencia de conceptos DIAN usado para sugerir vínculos automáticos |
| `backend/modulos/parametros` | Backend | Tabla de umbrales de declaración (UVT, topes) por año gravable; verificación de obligación de declarar |
| `backend/modulos/conciliacion` | Backend | Cruce de lo declarado contra `RegistroExogena`; borrador de valores sugeridos por renglón |
| `backend/modulos/cartera` | Backend | Vista consolidada: estado de obligación y de conciliación de todos los contribuyentes del contador |
| `backend/modulos/inventario` | Backend | CRUD de `Producto`, `Categoria`, `MetodoCosteo` |
| `backend/modulos/movimientos` | Backend | Registro de `Movimiento`, `Proveedor`, `DocumentoSoporte`; cálculo de costo de ventas |
| `backend/modulos/reportes` | Backend | Cierre de `PeriodoFiscal`, generación de kardex y exportables |
| `frontend/src/views` | Frontend | Pantallas por módulo, condicionadas al `tipoContribuyente` del contribuyente activo |
| `frontend/src/api` | Frontend | Definición de llamadas a la API y manejo del token JWT en cada petición |

## Por qué `parametros` y `cartera` son módulos aparte

`parametros` no pertenece a ningún contribuyente — es una tabla de
configuración (UVT y topes del año gravable) que cambia una vez al año por
resolución de la DIAN y que usan varios contribuyentes a la vez. Mezclarla
dentro de `contribuyentes` o `exogena` la haría más difícil de actualizar
sin tocar código de negocio.

`cartera` no gestiona ninguna entidad propia — es una capa de lectura que
agrega información que ya existe en `contribuyentes`, `parametros` y
`conciliacion` (obligación de declarar y alertas de cada contribuyente) para
mostrarla consolidada. Separarlo evita que ese agregado termine disperso
dentro de otro módulo que sí tiene responsabilidad de escritura.

## Criterio de organización

En el **backend**, cada módulo agrupa su propio modelo (SQLModel unifica
tabla y esquema de validación en una sola clase, a diferencia de separar
`models.py`/`schemas.py`), su `router.py` (endpoints) y su `servicios.py`
(lógica de negocio), siguiendo el mismo criterio de independencia por
incremento que ya se usaba en la versión anterior del proyecto: se puede
levantar y probar el módulo de contribuyentes sin que exista todavía el de
inventario.

En el **frontend**, `src/api/` concentra toda la comunicación con el
backend (incluida la inyección del token JWT en cada petición), de forma
que las vistas no conocen detalles de autenticación ni de URLs — solo
consumen funciones ya resueltas.

> **Nota**: esta estructura es la propuesta de organización para cuando
> inicie la implementación. Ver [09. Avances del
> proyecto](09-avances-proyecto.md) para el estado real de desarrollo a la
> fecha.
