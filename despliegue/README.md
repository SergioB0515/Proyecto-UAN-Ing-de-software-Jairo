# Desplegar en Render — paso a paso

Guía completa para dejar la aplicación en una URL pública, con los datos de
demostración cargados, lista para la sustentación.

Al final hay un apartado con las alternativas (VPS propio, Docker en local)
por si se necesitan.

---

## Antes de empezar: qué hay que tener

- Cuenta de GitHub con el repositorio **subido completo**. Hoy el repositorio
  público solo tiene `documentacion/` y el `README.md`: **el código no está
  ahí**, y Render despliega desde GitHub. El paso 1 arregla eso.
- Cuenta en [render.com](https://render.com) (el registro con GitHub es el
  más cómodo; no pide tarjeta para el plan gratuito).
- Estos archivos en la raíz del repositorio, que ya están:
  `Dockerfile`, `render.yaml`, `.dockerignore`.

---

## Paso 1 — Subir el código a GitHub

Desde la carpeta del proyecto:

```bash
git status                 # mira qué falta por subir
git add .
git commit -m "Implementación completa, empaquetado Docker y despliegue en Render"
git push origin main
```

Comprueba en GitHub que ahora se vean `backend/`, `frontend/`, `Dockerfile` y
`render.yaml` en la raíz. Si no están, el despliegue no puede funcionar.

Tres cosas que **no** deben subir, y que el `.gitignore` ya excluye:
`backend/.env`, `frontend/node_modules/`, `backend/almacen/`.

> Aprovecha para arreglar el `README.md` de la raíz: todavía dice que el
> proyecto está «en fase de diseño, implementación pendiente» y menciona el
> stack móvil viejo. Si el coordinador entra al repositorio, eso es lo
> primero que lee.

---

## Paso 2 — Crear el Blueprint en Render

1. Entra a [dashboard.render.com](https://dashboard.render.com).
2. Botón **New +** → **Blueprint**.
3. Conecta tu cuenta de GitHub si es la primera vez y autoriza el
   repositorio `Proyecto-UAN-Ing-de-software-Jairo`.
4. Selecciona el repositorio. Render detecta `render.yaml` y muestra lo que
   va a crear: un **Web Service** y una **PostgreSQL**.
5. Dale un nombre al grupo de recursos (por ejemplo `renta-uan`).
6. **Apply**.

No hay que escribir ninguna variable a mano. El `render.yaml` ya define:

| Variable | De dónde sale |
|---|---|
| `DATABASE_URL` | la conecta Render desde la base que crea (`fromDatabase`) |
| `JWT_SECRET_KEY` | la genera Render, aleatoria, y la conserva |
| `DEMO_RESET_TOKEN` | la genera Render |
| `SEMBRAR_DEMO_AL_ARRANCAR` | `1`, para que cargue los datos demo solo |
| `JWT_EXPIRACION_MINUTOS` | `120` |
| `PREFIJO_API` | viene dentro de la imagen (`/api`) |

---

## Paso 3 — Esperar el primer despliegue

Tarda bastante la primera vez: la imagen instala las dependencias de Node,
compila el SPA de Vue y después instala las de Python. Diez minutos no es
raro.

En la pestaña **Logs** del servicio verás, en este orden:

1. `npm ci` y `vite build` — compilación del frontend.
2. `pip install -r requirements.txt` — dependencias del backend.
3. `Uvicorn running on http://0.0.0.0:10000`.
4. Nada más: la aplicación crea las tablas y siembra los datos demo en
   silencio.

Render marca el despliegue como **Live** cuando `/salud` responde 200.

---

## Paso 4 — Entrar

`https://TU-SERVICIO.onrender.com`

```
Usuario:    contador@demo.co
Contraseña: demo1234
```

Deberías ver el panel de cartera con los seis contribuyentes: 4 obligados,
2 conceptos sin declarar, 1 vencida y 1 próxima a vencer.

Si eso aparece, el despliegue quedó bien.

---

## Paso 5 — Que no se duerma

Un servicio en plan Free **se suspende a los 15 minutos sin tráfico** y
despertarlo **tarda cerca de un minuto**. Eso, en plena sustentación, es un
minuto de pantalla en blanco.

Monta un ping en [cron-job.org](https://cron-job.org) (gratis, sin tarjeta):

- URL: `https://TU-SERVICIO.onrender.com/salud`
- Cada **10 minutos**
- Método GET

El plan Free da 750 horas de instancia al mes y un mes tiene 730, así que
**una sola** instancia siempre despierta cabe en el límite. Si levantas un
segundo servicio, las horas se acaban antes de fin de mes.

Aun con el ping, abre la URL diez minutos antes de presentar.

---

## Paso 6 — Guardar el token de reinicio

En el servicio → **Environment** → copia el valor de `DEMO_RESET_TOKEN` y
tenlo a mano. Si algo se daña a mitad de la demo:

```bash
curl -X POST https://TU-SERVICIO.onrender.com/api/demo/reiniciar \
     -H "X-Demo-Token: EL-TOKEN"
```

Devuelve los datos demo a su estado inicial en segundos.

---

## Lo que el plan Free no hace, y cómo afecta a esta aplicación

### Los adjuntos no sobreviven a un reinicio

No hay disco persistente en el plan Free: *«Paid services can preserve local
filesystem changes by attaching a persistent disk, but Free web services
cannot»*. Y como el servicio se recrea cada vez que despierta de la
suspensión, **los archivos subidos desaparecen**.

Por eso los cuatro soportes de la demo no se suben a mano: los genera
`semilla_demo.py` y la aplicación **los vuelve a crear en cada arranque si
faltan**. El módulo de soportes nunca aparece vacío.

Lo que sí se pierde es cualquier adjunto que subas tú durante la demo, en
cuanto el servicio se reinicie.

### La base de datos caduca a los 30 días

Una base Postgres en plan Free *«expira 30 días después de creada»*, con 14
días de gracia antes de que Render la borre. El reloj arranca el día que
apliques el Blueprint, y solo puede haber **una base Free activa por
workspace**.

Para esta aplicación pesa poco: **no hay datos propios que perder**. Todo lo
que vive en la base son los datos demo, y se reconstruyen solos al arrancar.
Si caduca, el costo es crear otra y reiniciar.

Aviso honesto: la documentación no dice si puedes crear una base Free nueva
después de que la primera caduque. No está comprobado. Si vas a depender de
eso, pruébalo antes y no el día de la sustentación.

### 512 MB de RAM

La aplicación carga pandas y reportlab, que no son livianos. Arranca bien,
pero procesar un Excel de exógena grande puede acercarse al límite. Si el
servicio se reinicia solo justo al subir un archivo, mira los logs: casi
seguro es memoria.

### Quitarse las tres de encima

En `render.yaml`, cambiar dos planes y añadir un disco:

```yaml
services:
  - type: web
    plan: starter          # $7/mes — deja de suspenderse
    disk:
      name: almacen
      mountPath: /datos/almacen
      sizeGB: 1
databases:
  - name: renta-db
    plan: basic-256mb      # ~$6/mes — deja de caducar
```

Unos $13/mes en total. Si el proyecto sigue vivo después de la entrega —y si
el coordinador lo evalúa como trabajo de grado, va a seguir vivo—, es lo
sensato.

---

## Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El build falla en `npm ci` | `package-lock.json` no está en GitHub o no coincide con `package.json` | `npm install` en local, commitear el lock y volver a subir |
| El build falla en `pip install` | una versión fijada de `requirements.txt` no existe para Python 3.12 | el log dice cuál; ajústala |
| Build eterno o cancelado | la primera vez es lenta de verdad | esperar; si pasa de 20 min, revisar logs |
| `Application failed to respond` | el contenedor arrancó pero `/salud` no responde | Logs: suele ser `JWT_SECRET_KEY` ausente o la base inalcanzable |
| `NoSuchModuleError: postgres` | la cadena llega como `postgres://` | ya está resuelto en `core/config.py`; si aparece, el archivo no se subió |
| Pantalla en blanco, la API responde | el SPA se construyó con un `VITE_API_URL` distinto de `PREFIJO_API` | los dos valen `/api` en el `Dockerfile`; no los cambies por separado |
| Abrir `/cartera` devuelve JSON | se perdió el prefijo `/api` | revisar que `PREFIJO_API=/api` siga en el `Dockerfile` |
| Login da 401 siempre | `JWT_SECRET_KEY` cambió entre despliegues | volver a entrar; los tokens viejos dejan de valer |
| El servicio se reinicia al subir un Excel | memoria | ver «512 MB de RAM» arriba |

Los logs están en el servicio → **Logs**, en vivo. Casi todo se diagnostica
ahí.

---

## Lista de verificación antes de la sustentación

- [ ] La URL abre y el login funciona desde **otro** computador o desde el
      celular con datos (no solo desde el tuyo).
- [ ] El ping de cron-job.org lleva al menos una hora corriendo.
- [ ] **Congelar el despliegue 24 horas antes.** Nada de subir cambios la
      mañana de la presentación: cada push redespliega.
- [ ] **Video de 2–3 minutos** con el flujo completo, **descargado en el
      portátil**. Si se cae internet, presentas el video.
- [ ] `docker compose up` probado en local el día anterior, en el portátil
      que vas a llevar. Tercer respaldo.
- [ ] Hotspot del celular listo: el wifi de la universidad es un punto único
      de falla que no controlas.
- [ ] Los Excel de `backend/demo/archivos/` descargados en el escritorio,
      para la carga en vivo.
- [ ] El `DEMO_RESET_TOKEN` y el comando de reinicio en una nota.
- [ ] Abrir la URL 10 minutos antes.

El guion de la demostración está en
[`backend/demo/README.md`](../backend/demo/README.md).

---

## Alternativas

### Correrlo en local con Docker

```bash
cp despliegue/variables-de-entorno.ejemplo .env   # y cambia las claves
docker compose up -d --build
```

Queda en `http://localhost:8000`. Sirve como respaldo de la demo y para
comprobar que la imagen construye antes de subirla.

### Un VPS propio (~€4/mes)

Un Hetzner CX22 con Docker Compose y Caddy delante. Siempre encendido, disco
persistente, nada caduca, y te sirve de práctica real de DevOps.

```bash
git clone <tu-repo> && cd Proyecto-UAN-Ing-de-software-Jairo
cp despliegue/variables-de-entorno.ejemplo .env   # claves y DOMINIO=...
sed -i 's/^PUERTO_PUBLICO=.*/PUERTO_PUBLICO=127.0.0.1:8000/' .env
docker compose --profile proxy up -d --build
```

Caddy pide y renueva el certificado HTTPS solo; solo hace falta el registro
DNS apuntando al servidor.

### Crédito de estudiante

El GitHub Student Developer Pack cambió este año: **DigitalOcean salió del
programa** (la oferta de $200 terminó el 31 de julio de 2026 y los créditos
redimidos expiraron el 1 de agosto). Lo que sigue sirviendo para alojar es el
crédito de **Azure** ($100) y el de **Heroku** ($13/mes por 24 meses, que
cubre un dyno Basic de $7 que no se duerme más Postgres Essential de $5).
Verifícalo en education.github.com/pack antes de contar con ello.

---

## Nota técnica: por qué la API va bajo `/api`

Las rutas de vue-router (`/cartera`, `/contribuyentes`, `/contribuyentes/3`)
son **las mismas** que las de la API. Sirviendo el SPA en el mismo origen sin
separarlas, abrir `/cartera` en el navegador devolvería JSON en vez de la
aplicación.

Por eso la API se monta bajo un prefijo configurable:

- `PREFIJO_API` (backend) y `VITE_API_URL` (build del frontend) valen `/api`
  en el contenedor. **Tienen que coincidir**; el `Dockerfile` los pone
  iguales.
- En desarrollo ambos quedan vacíos y todo sigue igual: Vite en 5173,
  FastAPI en 8000, y las pruebas llamando a `/contribuyentes`.
- `/salud` queda siempre en la raíz, sin prefijo, para el health check.

Además, `_SpaStaticFiles` devuelve `index.html` ante cualquier ruta que no
sea un archivo. Sin eso, recargar con F5 en `/contribuyentes/3/conciliacion`
daría 404.

---

Fuentes de los límites citados:
[Deploy for Free — Render docs](https://render.com/docs/free),
[GitHub Student Developer Pack](https://education.github.com/pack).
