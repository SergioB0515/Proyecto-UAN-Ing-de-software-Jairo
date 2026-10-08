from typing import List

from sqlmodel import Session, select

from core.excepciones import (
    CambioMetodoCosteoError,
    CategoriaConProductosActivosError,
    CategoriaNoEncontradaError,
    InventarioNoAplicaError,
    ProductoDuplicadoError,
    ProductoNoEncontradoError,
)

from ..contribuyentes.modelos import Contribuyente, TipoContribuyente
from ..contribuyentes.servicios import obtener_contribuyente
from ..movimientos.modelos import Movimiento
from .modelos import (
    Categoria,
    CategoriaCrear,
    Producto,
    ProductoActualizar,
    ProductoCrear,
)

TIPOS_CON_INVENTARIO = {TipoContribuyente.INDEPENDIENTE, TipoContribuyente.MIXTO}


def obtener_contribuyente_con_inventario(
    session: Session, contador_id: int, contribuyente_id: int
) -> Contribuyente:
    """Valida pertenencia al contador y que el contribuyente tenga negocio:
    un ASALARIADO no maneja inventario (HU-01)."""
    contribuyente = obtener_contribuyente(session, contador_id, contribuyente_id)
    if contribuyente.tipo_contribuyente not in TIPOS_CON_INVENTARIO:
        raise InventarioNoAplicaError(
            f"El contribuyente {contribuyente_id} es "
            f"{contribuyente.tipo_contribuyente.value}: el inventario solo "
            "aplica a INDEPENDIENTE o MIXTO"
        )
    return contribuyente


def _obtener_categoria(
    session: Session, contribuyente_id: int, categoria_id: int
) -> Categoria:
    categoria = session.get(Categoria, categoria_id)
    if categoria is None or categoria.contribuyente_id != contribuyente_id:
        raise CategoriaNoEncontradaError(
            f"No existe la categoría {categoria_id} para el contribuyente "
            f"{contribuyente_id}"
        )
    return categoria


# -------------------------------------------------------------------- Categoria


def crear_categoria(
    session: Session, contador_id: int, contribuyente_id: int, datos: CategoriaCrear
) -> Categoria:
    """HU-11."""
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    categoria = Categoria(**datos.model_dump(), contribuyente_id=contribuyente_id)
    session.add(categoria)
    session.commit()
    session.refresh(categoria)
    return categoria


def listar_categorias(
    session: Session, contador_id: int, contribuyente_id: int
) -> List[Categoria]:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    return list(
        session.exec(
            select(Categoria).where(Categoria.contribuyente_id == contribuyente_id)
        ).all()
    )


def eliminar_categoria(
    session: Session, contador_id: int, contribuyente_id: int, categoria_id: int
) -> None:
    """HU-11: no se elimina si tiene productos activos. Los inactivos quedan
    sin categoría — agregación, el producto no desaparece con ella."""
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    categoria = _obtener_categoria(session, contribuyente_id, categoria_id)

    productos = session.exec(
        select(Producto).where(Producto.categoria_id == categoria_id)
    ).all()
    if any(producto.activo for producto in productos):
        raise CategoriaConProductosActivosError(
            f"La categoría {categoria_id} tiene productos activos asociados"
        )

    for producto in productos:
        producto.categoria_id = None
        session.add(producto)
    session.delete(categoria)
    session.commit()


# --------------------------------------------------------------------- Producto


def crear_producto(
    session: Session, contador_id: int, contribuyente_id: int, datos: ProductoCrear
) -> Producto:
    """HU-11: la clasificación IVA y el método de costeo son obligatorios
    (los exige el esquema)."""
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    if datos.categoria_id is not None:
        _obtener_categoria(session, contribuyente_id, datos.categoria_id)

    existente = session.exec(
        select(Producto).where(
            Producto.contribuyente_id == contribuyente_id,
            Producto.codigo == datos.codigo,
        )
    ).first()
    if existente is not None:
        raise ProductoDuplicadoError(
            f"El contribuyente {contribuyente_id} ya tiene un producto con el "
            f"código {datos.codigo}"
        )

    producto = Producto(**datos.model_dump(), contribuyente_id=contribuyente_id)
    session.add(producto)
    session.commit()
    session.refresh(producto)
    return producto


def listar_productos(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    solo_activos: bool = False,
) -> List[Producto]:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    consulta = select(Producto).where(Producto.contribuyente_id == contribuyente_id)
    if solo_activos:
        consulta = consulta.where(Producto.activo == True)  # noqa: E712
    return list(session.exec(consulta).all())


def obtener_producto(
    session: Session, contador_id: int, contribuyente_id: int, producto_id: int
) -> Producto:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    producto = session.get(Producto, producto_id)
    if producto is None or producto.contribuyente_id != contribuyente_id:
        raise ProductoNoEncontradoError(
            f"No existe el producto {producto_id} para el contribuyente "
            f"{contribuyente_id}"
        )
    return producto


def actualizar_producto(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    producto_id: int,
    datos: ProductoActualizar,
) -> Producto:
    """Cambia solo los campos enviados. Desactivar (`activo=False`) es la
    forma de dar de baja un producto: no se borra, porque sus movimientos
    deben seguir siendo trazables."""
    producto = obtener_producto(session, contador_id, contribuyente_id, producto_id)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("categoria_id") is not None:
        _obtener_categoria(session, contribuyente_id, cambios["categoria_id"])

    nuevo_metodo = cambios.get("metodo_costeo")
    if nuevo_metodo is not None and nuevo_metodo != producto.metodo_costeo:
        tiene_movimientos = session.exec(
            select(Movimiento.id).where(Movimiento.producto_id == producto_id)
        ).first()
        if tiene_movimientos is not None:
            raise CambioMetodoCosteoError(
                f"El producto {producto_id} ya tiene movimientos: cambiar su "
                "método de costeo alteraría el costo de ventas ya calculado"
            )
    # None explícito en campos obligatorios no es un cambio válido.
    for campo in ("nombre", "clasificacion_iva", "metodo_costeo", "activo"):
        if campo in cambios and cambios[campo] is None:
            del cambios[campo]

    for campo, valor in cambios.items():
        setattr(producto, campo, valor)
    session.add(producto)
    session.commit()
    session.refresh(producto)
    return producto
