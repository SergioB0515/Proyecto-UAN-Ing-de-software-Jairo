# Migraciones del esquema

El esquema de la base lo construyen las revisiones de esta carpeta. Hasta la
revisión base lo construía `SQLModel.metadata.create_all()` más parches a mano
en `database.py`, y eso falló dos veces en el despliegue: `create_all` crea lo
que no existe y **no altera nada que ya exista**, así que una columna o un
valor de enum agregados después nunca llegaban a la base desplegada. El
detalle está en `documentacion/12-plan-inmediato.md`.

## Cambiar el esquema

```bash
cd backend
alembic revision --autogenerate -m "lo que cambiaste"
```

**Hay que leer lo que generó antes de subirlo.** `--autogenerate` compara los
modelos contra la base a la que esté apuntando y acierta con las tablas, las
columnas y los índices, pero no adivina qué hacer con los datos que ya
existen. Dos casos que hay que escribir a mano:

- Una columna `NOT NULL` nueva en una tabla con filas necesita un valor para
  esas filas: o `server_default`, o tres pasos (agregar nullable, poblar,
  poner NOT NULL).
- Renombrar algo sale como «borrar y crear», que pierde los datos. Se cambia
  por `op.alter_column(..., new_column_name=...)`.

No hace falta escribir `import sqlmodel` en cada revisión: la plantilla
`script.py.mako` ya lo trae, porque SQLModel tipa el texto como
`sqlmodel.sql.sqltypes.AutoString` y sin ese import la revisión falla con
`NameError`.

## Lo que impide que esto se desincronice

Alembic no obliga a nada por sí solo: si alguien cambia un modelo y no
escribe la revisión, le funciona en su máquina y se rompe en el despliegue.
Dos cosas en el CI lo atajan:

- **`herramientas/comprobar_revisiones.py`** crea una base vacía, le aplica
  `alembic upgrade head` y compara el resultado contra los modelos. Falla si
  falta una revisión, y dice qué falta.
- **`herramientas/prueba-actualizacion.sh`** crea el esquema con el código de
  la rama base, le siembra datos, migra con el código nuevo y corre la suite
  completa. Falla si la migración no funciona sobre una base que ya tenía
  filas, que es el caso que no se ve en local.

## El puente para las bases anteriores a Alembic

`database.crear_tablas()` distingue tres casos:

| Base | Qué hace |
|---|---|
| Vacía | `alembic upgrade head`: las revisiones la construyen entera |
| Con esquema y sin sellar | `_puente_a_alembic()` la lleva al baseline, la sella en la revisión base y aplica el resto |
| Ya sellada | `alembic upgrade head` |

La distinción importa: sellar una base sin su esquema la rompe para siempre,
porque Alembic creería que ya aplicó todo.

`_puente_a_alembic()` es el código viejo —`create_all` más los parches— y no
se convirtió en revisiones. No tendría sentido: una base nueva sale completa
de la revisión base, así que una revisión que agregara `fecha_corte` a
`reportes_exogena` sería un no-op o un error de columna duplicada. Eso no es
historia por registrar, es alcance para las bases que ya existían. Cuando no
quede ninguna sin sellar, esa función se puede borrar.

## Por qué `conftest.py` sigue usando `create_all`

Las pruebas crean el esquema con `create_all` y no con las revisiones, a
propósito. Prueban el comportamiento de la aplicación, no las migraciones; de
las migraciones se encargan las dos comprobaciones de arriba, que son más
precisas y no le agregan segundos a cada corrida de la suite.

Tiene un efecto útil y buscado: como `create_all` no toca una tabla que ya
existe, la suite corrida sobre una base migrada falla igual que falló
producción si quedó algo sin migrar. Por eso la prueba de actualización puede
usar la suite como verificación sin escribir una aserción por defecto posible.
