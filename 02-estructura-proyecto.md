# 2. Estructura del proyecto

Estructura de carpetas propuesta para la implementación en **Django**,
alineada con la arquitectura de tres capas (ver [04.
Arquitectura](04-arquitectura.md)) y con los módulos definidos en el modelo
de clases. Cada módulo de negocio corresponde a una **app de Django**.

```
app_renta_inventario/
│
├── docs/                        # Documentación del proyecto (este contenido)
│   ├── img/                     # Diagramas (clases, flujo, arquitectura)
│   └── *.md
│
├── manage.py                    # Punto de entrada de Django
├── requirements.txt             # Dependencias del proyecto (Django, mysqlclient, etc.)
│
├── config/                      # Configuración del proyecto Django
│   ├── settings.py              # Configuración general (incluye conexión a MySQL)
│   ├── urls.py                  # Enrutamiento principal
│   └── wsgi.py / asgi.py
│
├── apps/
│   ├── patrimonio/              # Contribuyente, Activo, FuenteIngreso
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── forms.py
│   │   ├── services.py          # Lógica de negocio (cálculo de patrimonio líquido)
│   │   ├── urls.py
│   │   └── templates/patrimonio/
│   │
│   ├── inventario/              # Producto, Categoria, MetodoCosteo
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── forms.py
│   │   ├── urls.py
│   │   └── templates/inventario/
│   │
│   ├── movimientos/             # Movimiento, Proveedor, DocumentoSoporte
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── forms.py
│   │   ├── services.py          # Lógica de negocio (cálculo de costeo PEPS/promedio)
│   │   ├── urls.py
│   │   └── templates/movimientos/
│   │
│   └── reportes/                # PeriodoFiscal, cierre, exportación
│       ├── models.py
│       ├── views.py
│       ├── services.py          # Generación de kardex, exportación Excel/PDF
│       ├── urls.py
│       └── templates/reportes/
│
├── templates/                   # Templates base compartidos (layout, navbar)
│   └── base.html
│
└── static/                      # CSS (Bootstrap), JS, imágenes
    ├── css/
    ├── js/
    └── img/
```

## Componentes principales

| App de Django | Responsabilidad |
|---|---|
| `apps/patrimonio` | CRUD de `Contribuyente`, `Activo`, `FuenteIngreso`; cálculo de patrimonio líquido |
| `apps/inventario` | CRUD de `Producto`, `Categoria`, `MetodoCosteo` |
| `apps/movimientos` | Registro de `Movimiento`, `Proveedor`, `DocumentoSoporte`; cálculo de costo de ventas |
| `apps/reportes` | Cierre de `PeriodoFiscal`, generación de kardex y exportables |

## Criterio de organización

Cada app agrupa sus propios modelos, vistas, formularios y templates, de
forma que los incrementos del [modelo de desarrollo](05-modelo-desarrollo.md)
puedan implementarse y probarse de forma independiente, sin que una app
bloquee a las demás. La lógica de negocio "pura" (cálculos de costeo,
patrimonio, cierre de periodo) se separa en un archivo `services.py` por
app, para no mezclarla con las vistas y facilitar las pruebas unitarias.

> **Nota**: esta estructura es la propuesta de organización para cuando
> inicie la implementación. Ver [09. Avances del
> proyecto](09-avances-proyecto.md) para el estado real de desarrollo a la
> fecha.
