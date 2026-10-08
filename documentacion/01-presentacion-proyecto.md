# 1. Presentación del proyecto

## Descripción general

En Colombia, toda persona natural o jurídica que cumpla con los topes de
patrimonio, ingresos o consumos definidos anualmente por la Dirección de
Impuestos y Aduanas Nacionales (DIAN) está obligada a presentar la
declaración de renta. Como control cruzado, la DIAN exige a terceros
(empleadores, bancos, clientes, proveedores, notarías) reportar las
operaciones que realizaron con cada contribuyente durante el año gravable.
Ese reporte consolidado se conoce como **información exógena**, y cualquier
contribuyente puede descargarlo (como archivo Excel) desde el portal
transaccional de la DIAN para verificar que coincide con lo que va a
declarar.

En la práctica, esa verificación —cruzar lo que el contribuyente declara
contra lo que terceros reportaron de él— la hace un **contador**, no el
contribuyente por su cuenta, y normalmente para varios clientes a la vez,
no para una sola persona.

Este proyecto desarrolla una aplicación web dirigida a **contadores**, que
les permite gestionar una cartera de contribuyentes (clientes) y, para cada
uno, mantener organizada la información de su patrimonio, sus ingresos y
(cuando aplique) su inventario, e importar su información exógena para
**conciliarla automáticamente** con lo registrado, señalando coincidencias
y discrepancias antes de la presentación de la declaración.

## Origen del alcance actual

El alcance de este documento reemplaza una versión anterior del proyecto,
pensada como app móvil de autogestión para un contribuyente individual. Tras
la presentación al profesor (Jairo), se replanteó el proyecto con tres
cambios de fondo:

1. La aplicación es **web**, no móvil.
2. El usuario que opera la aplicación es un **contador**, que gestiona
   contribuyentes en nombre de ellos — no el contribuyente mismo.
3. El objetivo central ya no es solo "ayudar a declarar", sino
   **comparar la información exógena de la DIAN contra la información
   propia del contribuyente para verificar que sean coincidentes**.

Tras revisar un archivo real de información exógena, el alcance se amplió
una segunda vez: además de señalar discrepancias, el sistema explota dos
datos que el archivo de la DIAN ya trae y que antes no se estaban
aprovechando — el resumen de topes por categoría (que permite verificar
automáticamente si el contribuyente está obligado a declarar) y el renglón
del formulario sugerido para cada concepto (que permite armar un borrador
de la declaración, no solo señalar diferencias).

## Objetivo general

Desarrollar una aplicación web que permita a un contador gestionar el
patrimonio, los ingresos y (cuando aplique) el inventario de sus
contribuyentes, e importar y conciliar la información exógena de la DIAN
contra esos registros, para facilitar la presentación de la declaración de
renta de cada uno.

## Objetivos específicos

- Permitir que un contador se autentique y gestione su propia cartera de
  contribuyentes (clientes).
- Registrar, por contribuyente, su patrimonio y sus fuentes de ingreso.
- Gestionar el inventario (productos, movimientos, costeo) de los
  contribuyentes con negocio.
- Importar el archivo de información exógena descargado de la DIAN y
  estructurarlo para su análisis.
- Determinar, a partir de los topes reportados en la exógena, si el
  contribuyente está obligado a declarar renta en el año gravable
  correspondiente.
- Conciliar automáticamente la información exógena importada contra lo
  registrado por el contador, señalando qué coincide, qué difiere y qué no
  fue declarado o no fue reportado por terceros.
- Generar un borrador de valores sugeridos por renglón de la declaración,
  a partir de los conceptos reportados en la exógena.
- Dar al contador una vista consolidada del estado de toda su cartera de
  contribuyentes, no solo de uno a la vez.
- Generar reportes de cierre de periodo fiscal, incluyendo el resultado de
  la conciliación, como soporte para la declaración de renta.

## Alcance

El proyecto cubre el diseño, modelado de datos, arquitectura y planeación
del desarrollo de la aplicación, ejecutado de forma incremental (ver
[Modelo de desarrollo](05-modelo-desarrollo.md)). El primer incremento
prioriza dejar operativo el ciclo mínimo de datos (contador → contribuyente
→ patrimonio); el segundo y el tercero priorizan la importación, la
verificación de obligación de declarar, la conciliación y el borrador de
renglones —por ser los requisitos centrales señalados por el profesor y los
que más valor agregan a un contador real—; el módulo de inventario, aunque
se mantiene, queda en un orden de prioridad posterior.

**Fuera de alcance**:

- Consultar o descargar la información exógena directamente desde la DIAN.
  La DIAN no expone una API pública para esto; el contador debe descargar
  el archivo Excel manualmente desde el portal transaccional de la DIAN y
  cargarlo en la aplicación.
- Presentación automática de la declaración ante la DIAN. La aplicación
  genera los reportes de soporte, el borrador de renglones y el resultado
  de la conciliación, pero no reemplaza el diligenciamiento del formulario
  oficial ni sustituye el criterio profesional del contador.
- Verificación completa de la obligación de declarar. El sistema evalúa los
  cinco topes monetarios (ingresos, patrimonio, consumos con tarjeta,
  compras y consignaciones) a partir de lo reportado en la exógena, pero
  **no** evalúa el criterio de "responsable de IVA durante el año", que no
  aparece en ese archivo y que el contador debe seguir verificando por su
  cuenta.
- Autogestión por parte del contribuyente: en este alcance, el
  contribuyente no tiene su propio inicio de sesión; todos los datos son
  cargados y gestionados por el contador. Ver nota de decisión en
  [04. Arquitectura](04-arquitectura.md).
- Cifrado en reposo de los campos más sensibles. La capa de auditoría
  (registro de accesos, bloqueo por intentos fallidos y registro de
  acciones) sí se implementó en el incremento 6; el cifrado de campos en
  la base de datos queda como extensión posible.
