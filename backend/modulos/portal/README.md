# Portal de carga del contribuyente

El contador genera un enlace desde la ficha del contribuyente. El
contribuyente lo abre en el celular, sin cuenta, acepta la política de
tratamiento de datos, sube el Excel de exógena que descargó de la DIAN y
responde, ítem por ítem, qué soportes tiene.

## Archivos

| Archivo | Qué hace |
|---|---|
| `politica.py` | La política de tratamiento, versionada. Las redacciones viejas se conservan. |
| `lenguaje_comun.py` | Traduce una fila de la exógena a una petición de documento en palabras. Sin base de datos. |
| `modelos.py` | `EnlaceCarga`, `AutorizacionTratamiento`, `RequerimientoDocumento`, `DatoAdicional`. |
| `servicios.py` | La lógica. No importa `liquidacion`, `conciliacion` ni `cartera`. |
| `router.py` | Endpoints del contador, con sesión. |
| `router_publico.py` | Lo único que un token permite hacer. |

## El enlace

- **Alcance:** un contribuyente y un periodo fiscal. Ninguna ruta pública
  recibe un `contribuyente_id` ni un `periodo_fiscal_id`: salen del enlace, así
  que no hay parámetro que validar ni que se pueda manipular.
- **Token:** `secrets.token_urlsafe(32)`. De él solo se guarda el SHA-256. El
  valor en claro viaja una sola vez, en la respuesta que lo crea. Si se pierde,
  se genera otro; no se puede recuperar.
- **Por qué SHA-256 y no Argon2:** el token son 256 bits generados por el
  sistema, no una contraseña elegida por una persona. No hay ataque de
  diccionario que encarecer, y un hash rápido permite buscar el enlace por
  igualdad sobre un índice.
- **Revocable:** `revocado_en`. Generar un enlace nuevo revoca los anteriores
  del mismo periodo, para que cada reenvío por WhatsApp no deje una puerta
  abierta más.
- **Reanudable:** abrirlo no lo consume. El contribuyente vuelve y encuentra
  sus respuestas y sus archivos donde los dejó.
- **Solo escribe:** no existe camino desde un token hasta la liquidación. No es
  una comprobación que haya que recordar hacer en cada endpoint: el código que
  la expondría no está importado en este módulo.

## La política

`AutorizacionTratamiento` guarda **qué versión** del texto aceptó el titular y
**cuándo**. Para publicar una redacción nueva se agrega una versión a
`politica.VERSIONES`; no se edita una existente. Si se editara, las
autorizaciones viejas quedarían respaldando un texto que nadie leyó.

Sin autorización registrada, ninguna ruta del portal escribe nada.

## Los requerimientos

Cada fila del archivo de la DIAN produce un requerimiento. **Ninguna se
descarta**, incluidas las que la aplicación no sabe clasificar: esas entran con
`concepto_reconocido = False` y un `motivo_revision`, y el contador las resuelve
desde su pestaña. Lo que no aparece en la conciliación es lo que después aparece
en un requerimiento de la DIAN.

El título usa el **nombre del tercero**, no el concepto tributario: el
contribuyente reconoce «Bancolombia», no reconoce «1110». Lo que se le pide sale
del propio `detalle` que escribe la DIAN, no de una tabla de códigos propia: los
códigos cambian de resolución en resolución.

Estados: `PENDIENTE`, `NO_APLICA`, `NO_LO_TENGO`, `NO_ENTIENDO`. **Cuatro, y
«cargado» no es uno de ellos**: tener un archivo es un hecho aparte del estado.
Se puede haber subido un papel y seguir sin entender de qué se trata, y esas dos
cosas le dicen al contador cosas distintas. `NO_ENTIENDO` no resuelve el ítem:
es el contribuyente pidiendo ayuda.

El estado es obligatorio y el valor opcional, en el servidor y en el formulario:
alguien puede saber que algo no le aplica sin saber la cifra.

Volver a cargar el archivo es idempotente. Los requerimientos se reconcilian por
la huella de la fila (tercero + concepto + detalle), que sí es estable entre
versiones, y **se conservan el estado, el valor informado, la nota y los
archivos**: son trabajo del contribuyente, no datos del archivo. Una fila que
desaparece de la versión nueva no se borra: se marca para revisión, porque que
un tercero retire un reporte es justo lo que el contador necesita ver.

## Los adicionales

Lo que la exógena nunca contiene: dependientes, intereses de vivienda, medicina
prepagada, AFC/AVP, activos, deudas y bienes del exterior.

Los topes se validan contra `parametros.tablas_oficiales`, versionada por año
gravable y con la norma citada al lado. **Ningún tope está escrito en el código
de este módulo**, y el formulario muestra los mismos que valida el servidor
porque los pide al mismo endpoint. Si el año no tiene parámetros cargados, el
formulario no se abre: validar contra topes que no existen es peor que no
validar.

Los conceptos que comparten tope se validan por la suma del grupo: los aportes
voluntarios a pensión y el ahorro en AFC no tienen 3.800 UVT cada uno, tienen
3.800 UVT entre los dos.

Cada adicional genera su propio requerimiento, para que no haya dos bandejas
distintas de «lo que falta».

## Los archivos

Van atados al requerimiento (`TipoEntidadAdjunto.REQUERIMIENTO`), no al periodo.
Así el contador abre el ítem y ve el papel que lo respalda, en vez de una
carpeta con treinta archivos y nadie que recuerde a qué correspondía cada uno.

## Bitácora

Lo que hace el contribuyente se audita **bajo el contador dueño del enlace**,
que es quien responde por esos datos. La ruta se guarda censurada: el token va
en la URL y escribirlo en la bitácora sería dejar la llave anotada en un
registro que se exporta, se respalda y se consulta desde la aplicación.

## Dónde entra en el resto de la aplicación

- `exogena`: el reporte ahora se versiona con su **fecha de corte**, que trae el
  propio archivo. El vigente es el de corte más reciente, no el último
  importado: si alguien sube hoy una consulta de marzo, los datos siguen siendo
  los de septiembre.
- `conciliacion`: los adicionales aterrizan en la **misma tabla** de cuatro
  estados, y `DecisionRenglon` guarda el valor final de cada renglón con la
  fuente elegida. Solo el contador la fija; el portal no tiene ruta equivalente.
- `cartera`: cada fila trae el estado de la recolección, para que el panel
  responda «a quién le falta qué» sin entrar a cada ficha.
