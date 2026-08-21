# 1. Presentación del proyecto

## Descripción general

En Colombia, toda persona natural o jurídica que cumpla con los topes de
patrimonio, ingresos o consumos definidos anualmente por la Dirección de
Impuestos y Aduanas Nacionales (DIAN) está obligada a presentar la
declaración de renta. Esta obligación no distingue un único tipo de
contribuyente: aplica tanto a quienes tienen un negocio con inventario de
mercancía, como a quienes reciben únicamente ingresos laborales
(asalariados) y deben declarar su patrimonio (vivienda, vehículo, cuentas,
inversiones).

Este proyecto desarrolla una aplicación de apoyo a ese proceso, dirigida a
**dos perfiles de usuario**:

1. **Contribuyentes con negocio** (comerciantes, productores o
   independientes), que además de su patrimonio general manejan inventario
   de mercancía.
2. **Contribuyentes asalariados**, que no tienen inventario pero sí deben
   registrar su patrimonio y sus fuentes de ingreso.

El módulo de inventario es, por lo tanto, un componente **opcional** dentro
de un sistema más amplio de apoyo a la declaración de renta.

## Objetivo general

Desarrollar una aplicación que permita a cualquier contribuyente colombiano
—tenga o no negocio— organizar la información de su patrimonio, sus
ingresos y (cuando aplique) su inventario, para facilitar la presentación de
su declaración de renta.

## Objetivos específicos

- Registrar el patrimonio y las fuentes de ingreso de cualquier
  contribuyente.
- Gestionar el inventario (productos, movimientos, costeo) de los
  contribuyentes con negocio.
- Calcular el costo de ventas según el método de costeo aceptado
  fiscalmente (PEPS o promedio ponderado).
- Generar reportes de cierre de periodo fiscal como soporte para la
  declaración de renta.

## Alcance

El proyecto cubre el diseño, modelado de datos, arquitectura propuesta y
planeación del desarrollo de la aplicación. La implementación se ejecuta de
forma incremental (ver [Modelo de desarrollo](05-modelo-desarrollo.md)),
comenzando por el módulo de patrimonio general, seguido del módulo de
inventario.

**Fuera de alcance**: presentación automática de la declaración ante la
DIAN (la aplicación genera los reportes de soporte, pero no reemplaza el
diligenciamiento del formulario oficial ni sustituye la asesoría de un
contador o abogado tributario).
