# 6. Historias de usuario

Historias de usuario organizadas por incremento (ver [05. Modelo de
desarrollo](05-modelo-desarrollo.md)), derivadas del [flujo de uso de la
aplicación](08-diagrama-flujo.md). El actor principal es el **contador**,
que opera la aplicación en nombre de sus contribuyentes (ver la decisión de
diseño en [04. Arquitectura](04-arquitectura.md)).

Desde el incremento 9 existe un segundo actor, el **contribuyente**, que
entra únicamente por el portal de carga, sin cuenta de usuario y con alcance
a un solo periodo. Aporta información y soportes; no decide cifras ni ve la
liquidación. Las historias indican en cada caso cuál de los dos actúa.

**Formato**: *Como [rol], quiero [acción], para [beneficio].*

---

## Épica 1 — Contador y contribuyentes (Incremento 1)

### HU-01 — Registrar e iniciar sesión como contador
**Como** contador,
**quiero** crear una cuenta y luego iniciar sesión con usuario y
contraseña,
**para** acceder de forma segura a la información de mis contribuyentes.

**Criterios de aceptación:**
- La contraseña se almacena con hash (`argon2`), nunca en texto plano.
- El inicio de sesión exitoso devuelve un token JWT.
- Un token inválido o expirado no permite acceder a ningún endpoint
  protegido.

### HU-02 — Registrar un contribuyente
**Como** contador,
**quiero** registrar un nuevo contribuyente con sus datos básicos (nombre,
RUT, tipo de contribuyente y régimen tributario),
**para** que la aplicación sepa qué módulos habilitarle.

**Criterios de aceptación:**
- El contribuyente queda asociado únicamente al contador que lo creó.
- El sistema exige seleccionar un `tipoContribuyente` (asalariado,
  independiente o mixto).
- Si el tipo es "asalariado", el módulo de inventario permanece oculto para
  ese contribuyente.

### HU-03 — Registrar fuentes de ingreso
**Como** contador,
**quiero** registrar las fuentes de ingreso de un contribuyente (salario,
honorarios, ventas, arriendos) con su retención en la fuente,
**para** tener consolidada la información de ingresos del año gravable.

**Criterios de aceptación:**
- Puedo registrar más de una fuente de ingreso por contribuyente.
- Cada fuente queda asociada a un periodo fiscal.
- El sistema valida que el valor anual sea mayor a cero.
- Opcionalmente puedo indicar un código de concepto DIAN o una palabra
  clave para vincular esta fuente con la información exógena (ver HU-08).

### HU-04 — Registrar activos patrimoniales
**Como** contador,
**quiero** registrar los activos de un contribuyente (cuentas, vehículos,
inmuebles, inversiones),
**para** que la aplicación calcule su patrimonio líquido.

**Criterios de aceptación:**
- Puedo clasificar cada activo por tipo (`CUENTA`, `VEHICULO`, `INMUEBLE`,
  `INVERSION`).
- El sistema calcula automáticamente el patrimonio líquido total sumando
  todos los activos del contribuyente.
- Opcionalmente puedo indicar un vínculo DIAN, igual que en HU-03.

---

## Épica 2 — Importación de exógena y obligación de declarar (Incremento 2)

### HU-05 — Importar el archivo de información exógena
**Como** contador,
**quiero** subir el archivo Excel de información exógena descargado de la
DIAN para un contribuyente y un año gravable,
**para** contar con lo reportado por terceros en un formato que la
aplicación pueda analizar.

**Criterios de aceptación:**
- El archivo queda asociado a un contribuyente y a un periodo fiscal
  específicos (`ReporteExogena`).
- La fila de encabezados se localiza buscando el contenido ("NIT" /
  "Nombre..."), no por un número de fila fijo.
- El bloque de "Topes" se reconoce y se guarda aparte de los registros de
  terceros (no se mezcla con `RegistroExogena`).
- Cada fila válida se guarda como un `RegistroExogena` con tercero,
  concepto (si el texto lo trae), renglón(es) sugerido(s) y valor.
- Las filas que no se puedan interpretar se reportan al contador,
  indicando el número de fila y el motivo, en vez de descartarse en
  silencio.

### HU-06 — Ver el detalle de lo importado
**Como** contador,
**quiero** ver el listado de registros importados de un
`ReporteExogena`, agrupados por concepto y tercero,
**para** revisar qué se cargó antes de conciliarlo.

**Criterios de aceptación:**
- El listado se puede filtrar por concepto y por tercero reportante.
- Las filas autoreportadas o reportadas por la propia DIAN se distinguen
  visualmente de las de un tercero genuino.

### HU-07 — Ver si el contribuyente está obligado a declarar
**Como** contador,
**quiero** ver, apenas importo la exógena de un contribuyente, si está
obligado a declarar renta ese año,
**para** priorizar a qué clientes atender primero sin tener que revisar
cada tope a mano.

**Criterios de aceptación:**
- El sistema compara los cinco topes del archivo (ingresos, patrimonio,
  consumo con tarjeta, compras, movimiento) contra la tabla de umbrales
  vigente para ese año gravable.
- Basta con que uno de los cinco supere su umbral para marcar al
  contribuyente como obligado.
- La tabla de umbrales es un dato configurable por año gravable, no un
  valor fijo en el código.
- El resultado se muestra siempre acompañado de una nota indicando que no
  evalúa el criterio de responsable de IVA, y que no reemplaza la
  verificación del contador.

---

## Épica 3 — Conciliación y borrador de renglones (Incremento 3)

### HU-08 — Conciliar la información exógena contra lo declarado
**Como** contador,
**quiero** ejecutar la conciliación entre lo importado de la DIAN y lo que
registré para un contribuyente,
**para** identificar coincidencias y discrepancias antes de la
declaración.

**Criterios de aceptación:**
- Cada activo o fuente de ingreso con vínculo DIAN se cruza contra los
  `RegistroExogena` correspondientes; cada uno queda clasificado como
  `COINCIDE`, `DISCREPANCIA` o `NO_REPORTADO_POR_TERCERO`.
- Todo `RegistroExogena` relevante que no quedó vinculado a ningún ítem
  declarado aparece como `NO_DECLARADO`.
- Las filas autoreportadas, las reportadas por la propia DIAN, y las de
  retención asociadas a un ingreso ya cruzado, quedan excluidas del cruce.
- La conciliación no modifica ningún dato ya registrado; es un reporte de
  solo lectura.

### HU-09 — Ver el reporte de conciliación
**Como** contador,
**quiero** ver un reporte consolidado de la conciliación de un
contribuyente,
**para** decidir con él qué corregir antes de presentar la declaración.

**Criterios de aceptación:**
- El reporte muestra, por concepto: valor declarado, valor reportado por
  terceros, diferencia y estado.
- El reporte se puede exportar (ver Épica 5).

### HU-10 — Ver el borrador de valores sugeridos por renglón
**Como** contador,
**quiero** ver los valores de la exógena agrupados por renglón del
formulario de declaración,
**para** tener un punto de partida ya sumado en vez de armar esa suma a
mano concepto por concepto.

**Criterios de aceptación:**
- Los renglones se extraen de la columna "Uso declaración Sugerida" de
  cada `RegistroExogena`.
- El borrador se presenta claramente como una sugerencia editable, no como
  el valor final a declarar.

---

## Épica 4 — Inventario (Incremento 4)

### HU-11 — Crear categorías y productos
**Como** contador,
**quiero** crear categorías y registrar productos para un contribuyente
con negocio, con su clasificación fiscal de IVA y su método de costeo,
**para** que el sistema calcule correctamente el valor de su inventario.

**Criterios de aceptación:**
- No se puede eliminar una categoría con productos activos asociados
  (relación de **agregación**, no de composición).
- Cada producto exige una clasificación IVA (`GRAVADO`, `EXENTO`,
  `EXCLUIDO`) y un `MetodoCosteo` (PEPS o promedio ponderado).

### HU-12 — Registrar movimientos de inventario
**Como** contador,
**quiero** registrar cada compra o venta de mercancía de un contribuyente
con negocio, adjuntando su documento soporte,
**para** mantener actualizado su stock y contar con el soporte documental.

**Criterios de aceptación:**
- No se puede registrar un movimiento sin `DocumentoSoporte` asociado.
- El sistema valida que haya stock suficiente antes de registrar una
  salida.
- El `valorTotal` del movimiento se calcula automáticamente.

### HU-13 — Registrar proveedores
**Como** contador,
**quiero** registrar los proveedores de un contribuyente con negocio,
**para** asociar cada compra con el tercero que la originó.

**Criterios de aceptación:**
- Puedo clasificar al proveedor como persona natural o jurídica.
- El sistema exige un número de identificación único por proveedor.

### HU-14 — Calcular el costo de ventas
**Como** contador,
**quiero** que el sistema calcule automáticamente el costo de ventas de un
contribuyente según el método de costeo de cada producto,
**para** no tener que hacer el cálculo manualmente y evitar errores.

**Criterios de aceptación:**
- Si el método es PEPS, las salidas se costean con las entradas más
  antiguas disponibles.
- Si el método es promedio ponderado, el sistema recalcula el costo
  promedio en cada entrada.

---

## Épica 5 — Cierre, reportes y cartera (Incremento 5)

### HU-15 — Cerrar el periodo fiscal
**Como** contador,
**quiero** cerrar el periodo fiscal de un contribuyente al finalizar el
año gravable,
**para** consolidar sus movimientos y dejar el inventario listo para
declarar.

**Criterios de aceptación:**
- Al cerrar el periodo, no se pueden registrar más movimientos ni importar
  más exógena para ese año.
- El valor final del inventario se refleja como un activo dentro del
  patrimonio del contribuyente.

### HU-16 — Generar reportes de cierre
**Como** contador,
**quiero** generar el kardex, el saldo de inventario, el reporte de
conciliación y el borrador de renglones de un contribuyente,
**para** contar con el soporte necesario para su declaración de renta.

**Criterios de aceptación:**
- El kardex muestra el histórico de movimientos por producto.
- Los reportes se pueden exportar en Excel y en PDF.

### HU-17 — Ver reportes consolidados por contribuyente
**Como** contador,
**quiero** ver en un solo lugar el patrimonio, los ingresos, el inventario
(si aplica), el estado de obligación de declarar y el estado de
conciliación de un contribuyente,
**para** tener toda la información lista antes de su declaración.

**Criterios de aceptación:**
- La vista se adapta según `tipoContribuyente`: un asalariado no muestra
  secciones de inventario.
- El resumen indica claramente a qué periodo fiscal corresponde la
  información mostrada.

### HU-18 — Ver el panel de cartera
**Como** contador,
**quiero** ver, para todos mis contribuyentes a la vez, si están
obligados a declarar y cuántas alertas de conciliación tiene cada uno,
**para** priorizar a quién atender primero sin entrar contribuyente por
contribuyente.

**Criterios de aceptación:**
- El panel lista todos los contribuyentes del contador autenticado, nunca
  los de otro contador.
- Por cada contribuyente se muestra: estado de obligación de declarar y
  número de registros en estado `NO_DECLARADO`.
- El panel permite ordenar por número de alertas, para priorizar los casos
  más urgentes.

---

## Épica 6 — Seguridad y trazabilidad (Incremento 6)

### HU-19 — Proteger la cuenta contra intentos de acceso
**Como** contador,
**quiero** que mi cuenta se bloquee temporalmente tras varios intentos
fallidos de inicio de sesión y poder ver los accesos a ella,
**para** que nadie pueda adivinar mi contraseña probando muchas veces.

**Criterios de aceptación:**
- Con 5 intentos fallidos en 15 minutos el email queda bloqueado hasta que
  el más antiguo de esos fallos salga de la ventana, aunque luego se use la
  contraseña correcta.
- El bloqueo aplica también a emails que no existen, para no revelar qué
  cuentas están registradas.
- Puedo ver mis últimos accesos (exitosos, fallidos y bloqueados) con su
  dirección IP.

### HU-20 — Cambiar mi contraseña
**Como** contador,
**quiero** cambiar mi contraseña indicando la actual,
**para** proteger mi cuenta si sospecho que alguien la conoce.

**Criterios de aceptación:**
- Se exige la contraseña actual.
- La nueva cumple la política: 8 caracteres o más, con letras y números
  (la misma que al registrarse).

### HU-21 — Consultar la actividad registrada
**Como** contador,
**quiero** ver qué cambios hice sobre los datos y qué reportes descargué,
con fecha e IP, y filtrarlos por contribuyente,
**para** tener trazabilidad sobre información tributaria sensible.

**Criterios de aceptación:**
- Toda acción que modifica datos o descarga un reporte queda registrada
  automáticamente; las que fallan, no.
- Cada contador ve solo su propia actividad.

## Épica 7 — Calidad de vida (Incremento 7)

### HU-22 — Corregir o eliminar registros
**Como** contador,
**quiero** editar o eliminar activos, ingresos y contribuyentes,
**para** corregir errores de digitación.

**Criterios de aceptación:**
- Activos e ingresos solo se corrigen o eliminan con el periodo abierto.
- El inventario que registra el cierre no se modifica a mano.
- Un contribuyente solo se elimina si no tiene años gravables ni
  inventario registrados.

### HU-23 — Copiar los activos del año anterior
**Como** contador,
**quiero** traer a un año gravable nuevo los activos del año anterior,
**para** no volver a digitar bienes que se mantienen (vivienda, vehículo,
cuentas).

**Criterios de aceptación:**
- Se copian con su valor y su vínculo DIAN; el contador actualiza los
  valores al 31 de diciembre.
- No se copia el inventario del cierre ni se duplican activos ya
  existentes.

### HU-24 — Declarar desde la conciliación
**Como** contador,
**quiero** registrar con un clic un concepto que la exógena reporta y no
está declarado,
**para** corregir la diferencia sin volver a digitar valores.

**Criterios de aceptación:**
- El formulario llega prellenado con el detalle, el valor y el código de
  concepto; puedo elegir si es un activo o un ingreso.
- Al guardarlo, la conciliación se recalcula y el concepto deja de
  aparecer como no declarado.

## Épica 8 — Seguimiento de la declaración (Incremento 8)

### HU-25 — Saber cuándo vence la declaración de cada contribuyente
**Como** contador,
**quiero** que la aplicación calcule la fecha límite de cada declaración
según los dos últimos dígitos del NIT,
**para** atender primero a los clientes cuyo plazo está por vencer.

**Criterios de aceptación:**
- El calendario de vencimientos se registra por año gravable; la
  aplicación trae el oficial de la DIAN para los años verificados y
  permite registrar otros a mano.
- Se usan los dos últimos dígitos del NIT sin el dígito de verificación.
- El panel de cartera muestra la fecha límite y el estado (pendiente,
  próxima a vencer en 15 días, vencida, presentada) y se puede ordenar
  por fecha límite.

### HU-26 — Registrar la presentación y fechas especiales
**Como** contador,
**quiero** marcar la declaración de un año como presentada y, si la DIAN
fija un plazo especial para un contribuyente, registrar esa fecha,
**para** que las alertas reflejen la situación real.

**Criterios de aceptación:**
- Una declaración presentada deja de generar alertas.
- La fecha especial reemplaza a la del calendario y se puede quitar.
- Se puede registrar aunque el periodo esté cerrado.

### HU-27 — Exportar la cartera
**Como** contador,
**quiero** descargar el panel de cartera en Excel o PDF,
**para** compartir el estado de mis clientes o trabajarlo por fuera de la
aplicación.

**Criterios de aceptación:**
- La exportación respeta el año y el orden elegidos en el panel.
- La descarga queda registrada en la actividad.

---

## Épica 9 — Portal del contribuyente (Incremento 9)

Hasta aquí el contador capturaba todo. Esta épica traslada al contribuyente
la parte que solo él puede aportar —sus soportes y lo que la exógena no
registra— sin darle cuenta de usuario y sin exponerle la liquidación.

### HU-28 — Generar un enlace de carga para un contribuyente
**Como** contador,
**quiero** generar desde la ficha de un contribuyente un enlace con el que
pueda aportar su información de un periodo,
**para** dejar de perseguir documentos por correo y por mensajería.

**Criterios de aceptación:**
- El token se genera aleatorio y se almacena con hash; el valor en claro se
  devuelve una sola vez, al crearlo.
- El enlace tiene alcance a un contribuyente y un periodo: no sirve para
  otro.
- Generar un enlace nuevo revoca los que estuvieran vigentes para ese
  periodo.
- El enlace tiene fecha de expiración y puede reanudarse: el contribuyente
  cierra la página y vuelve sin perder lo cargado.

### HU-29 — Autorizar el tratamiento de mis datos
**Como** contribuyente,
**quiero** leer y aceptar la política de tratamiento antes de entregar nada,
**para** saber para qué se usan mis datos y quién responde por ellos.

**Criterios de aceptación:**
- Queda registrada la versión del texto aceptado y la fecha.
- Las versiones de la política se agregan, nunca se editan: una autorización
  vieja sigue respaldando el texto que se leyó.
- Sin autorización registrada, ninguna ruta del portal escribe nada.
- El nombre y el documento que se escriben se comparan contra los que el
  contador tiene registrados; si no corresponden, la aceptación se rechaza y
  no se guarda nada.
- El mensaje de rechazo no revela el valor registrado.

### HU-30 — Cargar el archivo de la DIAN desde el enlace
**Como** contribuyente,
**quiero** subir el Excel de información exógena que descargué del portal de
la DIAN,
**para** que la lista de documentos que me piden salga de ahí y no tenga que
adivinarla.

**Criterios de aceptación:**
- El archivo se guarda versionado y con su fecha de corte.
- Cargar un archivo más reciente no borra lo ya respondido ni los soportes
  cargados.
- Si el archivo no tiene el formato esperado, se indica la fila y el motivo.

### HU-31 — Saber qué documentos me piden, en lenguaje común
**Como** contribuyente,
**quiero** ver la lista de documentos descrita con el nombre de quien reportó
y no con el concepto tributario,
**para** entender qué me están pidiendo sin saber de impuestos.

**Criterios de aceptación:**
- Cada documento se identifica por el tercero que reportó, no por el código
  del concepto.
- Los conceptos que la aplicación no reconoce no se descartan: se piden
  igual y quedan marcados para el contador.
- La lista es la misma que ve el contador; no hay dos bandejas de pendientes.

### HU-32 — Responder cada documento aunque no lo tenga
**Como** contribuyente,
**quiero** marcar cada documento como pendiente, no aplica, no lo tengo o no
entiendo,
**para** que mi contador sepa en qué va cada punto aunque yo no pueda
resolverlo.

**Criterios de aceptación:**
- El estado es obligatorio; el valor es opcional.
- Lo marcado como «no entiendo» no cuenta como resuelto y queda señalado para
  el contador.
- Cada respuesta queda registrada en la actividad, atribuida al contador
  dueño del enlace y sin guardar el token.

### HU-33 — Subir los soportes desde el celular
**Como** contribuyente,
**quiero** tomar una foto o adjuntar un archivo desde el teléfono, sin crear
una cuenta,
**para** aportar los soportes donde los tengo y cuando los tengo.

**Criterios de aceptación:**
- El archivo queda atado al documento que lo motivó, no suelto en una carpeta.
- Subir un soporte deja el documento como recibido, sin pedir un paso
  adicional.
- El portal no muestra en ningún momento la liquidación ni el impuesto.

### HU-34 — Registrar lo que la exógena no trae
**Como** contribuyente,
**quiero** registrar mis dependientes, intereses de vivienda, medicina
prepagada, aportes AFC o de pensión voluntaria, activos, deudas y bienes del
exterior,
**para** que entren a la declaración, porque ningún tercero se los reporta a
la DIAN.

**Criterios de aceptación:**
- Los valores se validan contra una tabla de parámetros fiscales versionada
  por año gravable, no contra topes escritos en el código.
- Los conceptos que comparten tope se validan por la suma del grupo.
- Lo registrado aquí entra a la misma tabla de conciliación que el resto.

### HU-35 — Fijar el valor final de cada renglón
**Como** contador,
**quiero** decidir el valor final de cada renglón y que quede registrado de
qué fuente salió,
**para** que la decisión sea mía y quede explicada.

**Criterios de aceptación:**
- Todo aterriza en una sola tabla con cuatro estados: coincide, diferencia,
  solo en exógena y solo en declarado.
- Solo el contador fija el valor final; el contribuyente informa y aporta
  soportes.
- Al elegir exógena o declarado, el valor lo pone la fila y no el cuerpo de
  la petición: no se puede registrar «elegí la exógena» junto a otra cifra.
- Queda registrado qué fuente se eligió, cuándo y con qué nota.

### HU-36 — Revocar un enlace de carga
**Como** contador,
**quiero** revocar un enlace que ya no debe servir,
**para** cortar el acceso si se envió por error o si el periodo ya se cerró.

**Criterios de aceptación:**
- Un enlace revocado o expirado responde con un estado propio, distinto del
  de un enlace que nunca existió.
- Lo ya cargado no se pierde al revocar.
