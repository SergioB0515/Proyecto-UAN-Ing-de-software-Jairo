# Portal de carga del contribuyente

El contador genera un enlace desde la ficha del contribuyente. El
contribuyente lo abre en el celular, sin cuenta, acepta la política de
tratamiento de datos, sube el Excel de exógena que descargó de la DIAN y
responde, documento por documento, qué tiene y qué no.

## Lo que este módulo NO tiene

**La lista de documentos.** Esa es la del módulo `gestion`
(`DocumentoSolicitado`), que ya la derivaba de la exógena, de las deducciones
solicitadas y de la hoja de liquidación. El portal es la cara que ve el
contribuyente de esa misma lista.

Vale la pena decir por qué, porque la primera versión de este módulo sí tenía
su propia tabla de requerimientos y estaba peor:

- `gestion` **deduplica por tercero y tipo**: si Bancolombia reporta tres
  filas del mismo tipo, se pide un certificado, no tres.
- `gestion` **deriva la lista al vuelo** y solo guarda fila cuando alguien
  decidió o cargó algo, así que no puede quedar con filas obsoletas de una
  versión anterior del archivo.
- `gestion` cubre además las deducciones solicitadas, los dependientes, las
  deudas y la declaración del año anterior, no solo la exógena.

Dos tablas de documentos pedidos significan dos cuentas de «lo que falta» que
se separan en cuanto alguien marca algo en una sola.

Lo que el portal **le agregó** a esa lista: dos estados que solo puede marcar
el contribuyente (`NO_LO_TENGO`, `NO_ENTIENDO`), los archivos atados a cada
documento, el valor que él informa, y la marca de quién puso el estado.

## Archivos

| Archivo | Qué hace |
|---|---|
| `politica.py` | La política de tratamiento, versionada. Las redacciones viejas se conservan. |
| `modelos.py` | `EnlaceCarga`, `AutorizacionTratamiento`, `DatoAdicional`. |
| `servicios.py` | El enlace, la política, los adicionales. Los documentos los delega a `gestion`. |
| `router.py` | Endpoints del contador: enlace y adicionales. Los documentos los atiende el router de `gestion`. |
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
- **Solo escribe:** por el enlace no sale la liquidación. Antes eso se
  sostenía por los imports de `servicios.py`; ahora la lista de documentos
  viene de `gestion`, que sí lee la liquidación para saber qué pedir, así que
  la garantía se verifica donde importa: `test_portal` recorre el esquema de
  todas las respuestas de `/carga/...` y falla si alguna arrastra un campo de
  liquidación. Es más fuerte que la anterior, porque sobrevive a que alguien
  agregue un import.

## La política

`AutorizacionTratamiento` guarda **qué versión** del texto aceptó el titular y
**cuándo**. Para publicar una redacción nueva se agrega una versión a
`politica.VERSIONES`; no se edita una existente. Si se editara, las
autorizaciones viejas quedarían respaldando un texto que nadie leyó.

Sin autorización registrada, ninguna ruta del portal escribe nada.

### Que quien acepta sea el titular

Antes de guardar la autorización se comparan el nombre y el documento que
escribió quien la acepta contra los que el contador tiene registrados
(`verificar_identidad`). Si no corresponden, la aceptación se rechaza con 422
y no queda nada guardado.

Esto no es una barrera de acceso: quien abre el enlace ya lo tiene. Es que la
autorización de tratamiento solo vale si la dio el titular de los datos. Un
enlace se reenvía, y el contador se puede equivocar de cliente al mandarlo:
sin la comprobación, quien lo abra deja una autorización firmada con su
nombre en la carpeta de un tercero.

Cómo se comparan:

- **Documento**, solo por sus dígitos: los puntos y los guiones son formato.
  Se tolera un dígito de más al final, porque un NIT se registra a veces con
  su dígito de verificación y se escribe sin él. Esta es la comprobación que
  de verdad sostiene la autorización: el portal solo muestra los últimos
  cuatro dígitos, así que el número completo lo sabe el titular.
- **Nombre**, por palabras, sin tildes ni mayúsculas y sin conectores. Uno de
  los dos conjuntos tiene que estar contenido en el otro, con dos palabras en
  común: así pasa quien escribe los cuatro nombres de la cédula cuando el
  contador registró dos, y quien escribe dos cuando el contador registró
  cuatro, pero no quien cambia un apellido. El nombre figura en la pantalla,
  de modo que confirma pero no prueba.

El mensaje de error **nunca devuelve el valor registrado**. Decir cuál era el
documento esperado convertiría el enlace en una forma de averiguar la cédula
del titular; `test_el_error_no_revela_el_documento_registrado` lo verifica.

## Los documentos, desde el lado del cliente

Estados (`gestion.EstadoDocumento`): `PENDIENTE`, `RECIBIDO`, `NO_APLICA`,
`NO_LO_TENGO`, `NO_ENTIENDO`.

- Los tres primeros los marca el contador, o los deduce la aplicación:
  **subir un archivo deja el documento en RECIBIDO**, porque subir el papel ES
  recibirlo y pedirle además al cliente que marque un estado sería
  preguntarle dos veces lo mismo.
- Los dos últimos solo los marca el contribuyente. Son las dos respuestas que
  antes llegaban por WhatsApp y se perdían.
- `NO_ENTIENDO` **no cierra el documento**: es el contribuyente pidiendo
  ayuda, y la pelota queda del lado del contador. `resuelto` lo refleja.

El estado es obligatorio y el valor opcional: alguien puede saber que algo no
le aplica sin saber la cifra.

Los conceptos de la exógena que ninguna regla reconoce **no se descartan**:
entran con un soporte genérico y `reconocido = False`, y el contador los ve
marcados. Lo que no aparece en la lista es lo que después aparece en un
requerimiento de la DIAN.

Recargar el archivo conserva todo: la lista se deriva del reporte cada vez que
se consulta y la tabla solo guarda lo que alguien decidió o cargó, así que no
hay nada que sincronizar y no puede quedar nada obsoleto.

## Los adicionales

Lo que la exógena nunca contiene: dependientes, intereses de vivienda,
medicina prepagada, AFC/AVP, activos, deudas y bienes del exterior.

Los topes se validan contra `parametros.tablas_oficiales`, versionada por año
gravable y con la norma citada al lado. **Ningún tope está escrito en el código
de este módulo**, y el formulario muestra los mismos que valida el servidor
porque los pide al mismo endpoint. Si el año no tiene parámetros cargados, el
formulario no se abre: validar contra topes que no existen es peor que no
validar.

Los conceptos que comparten tope se validan por la suma del grupo: los aportes
voluntarios a pensión y el ahorro en AFC no tienen 3.800 UVT cada uno, tienen
3.800 UVT entre los dos.

Registrar un adicional **no crea una petición aparte**: `gestion` deriva de él
el soporte que hay que pedir (el certificado de medicina prepagada, los
soportes de los dependientes), así que la lista de documentos se actualiza
sola y sigue siendo una sola. Un activo o un bien en el exterior no generan
petición: valen lo que valen y entran a la conciliación, no hay un certificado
estándar que pedir por ellos.

## Los archivos

Van atados al documento (`TipoEntidadAdjunto.DOCUMENTO_SOLICITADO`), no al
periodo. Así el contador abre el ítem y ve el papel que lo respalda, en vez de
una carpeta con treinta archivos y nadie que recuerde a qué correspondía cada
uno.

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
- `gestion`: le aporta los dos estados del cliente, los archivos, el valor
  informado y la marca `reconocido`.
- `conciliacion`: los adicionales aterrizan en la **misma tabla** de cuatro
  estados, y `DecisionRenglon` guarda el valor final de cada renglón con la
  fuente elegida. Solo el contador la fija; el portal no tiene ruta equivalente.
- `cartera`: cada fila trae el estado de la recolección, para que el panel
  responda «a quién le falta qué» sin entrar a cada ficha.
