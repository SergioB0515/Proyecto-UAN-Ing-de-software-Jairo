"""Pruebas de las migraciones que corren al arrancar.

El esquema se crea con `create_all`, que solo sabe crear lo que no existe.
Todo lo que cambia en una tabla o un tipo que YA existe hay que migrarlo a
mano, y nada de eso se nota en las pruebas normales: cada corrida parte de
una base nueva, donde el esquema sale completo de una vez. Por eso estas
pruebas miran el metadata y no la base.
"""

from sqlalchemy import create_engine

from database import _sincronizar_enums, tipos_enum_nativos


def test_los_enums_nativos_se_leen_del_metadata():
    """Lo que protege del 500 que apareció en el despliegue.

    En Postgres estos enums son tipos nativos que `create_all` crea una vez y
    no vuelve a tocar. La sincronización saca del metadata los valores que
    debería tener cada tipo, así que esta prueba falla si alguien agrega un
    valor a un enum de una forma que el sincronizador no alcance a ver.
    """
    tipos = tipos_enum_nativos()

    assert "NO_LO_TENGO" in tipos["estadodocumento"]
    assert "NO_ENTIENDO" in tipos["estadodocumento"]
    assert "DOCUMENTO_SOLICITADO" in tipos["tipoentidadadjunto"]


def test_se_recorren_todos_los_tipos_y_no_una_lista_escrita_a_mano():
    """Una lista a mano hay que acordarse de actualizarla; el metadata no."""
    tipos = tipos_enum_nativos()

    assert len(tipos) > 10
    assert "categoriaadjunto" in tipos


def test_sincronizar_enums_no_toca_nada_fuera_de_postgres():
    """En SQLite el enum es un VARCHAR con CHECK: no hay tipo que alterar."""
    _sincronizar_enums(create_engine("sqlite://"))
