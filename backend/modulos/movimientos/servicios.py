from typing import List, Optional

from sqlmodel import Session, select

from core.excepciones import (
    DocumentoSoporteDuplicadoError,
    DocumentoSoporteNoEncontradoError,
    MovimientoInvalidoError,
    PeriodoFiscalCerradoError,
    ProductoInactivoError,
    ProveedorDuplicadoError,
    ProveedorNoEncontradoError,
)

from ..contribuyentes.modelos import EstadoPeriodo
from ..contribuyentes.servicios import obtener_periodo_fiscal
from ..inventario.modelos import Producto
from ..inventario.servicios import (
    obtener_contribuyente_con_inventario,
    obtener_producto,
)
from . import costeo
from .modelos import (
    CostoVentasPeriodo,
    CostoVentasProducto,
    DocumentoSoporte,
    DocumentoSoporteCrear,
    Kardex,
    KardexProductoPeriodo,
    Movimiento,
    MovimientoCrear,
    Proveedor,
    ProveedorCrear,
    TipoMovimiento,
)


def crear_proveedor(
    session: Session, contador_id: int, contribuyente_id: int, datos: ProveedorCrear
) -> Proveedor:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    identificacion = datos.identificacion.strip()
    existente = session.exec(
        select(Proveedor).where(
            Proveedor.contribuyente_id == contribuyente_id,
            Proveedor.identificacion == identificacion,
        )
    ).first()
    if existente is not None:
        raise ProveedorDuplicadoError(
            f"Ya existe un proveedor con la identificación {identificacion}"
        )

    proveedor = Proveedor(
        **datos.model_dump(exclude={"identificacion"}),
        identificacion=identificacion,
        contribuyente_id=contribuyente_id,
    )
    session.add(proveedor)
    session.commit()
    session.refresh(proveedor)
    return proveedor


def listar_proveedores(
    session: Session, contador_id: int, contribuyente_id: int
) -> List[Proveedor]:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    return list(
        session.exec(
            select(Proveedor)
            .where(Proveedor.contribuyente_id == contribuyente_id)
            .order_by(Proveedor.nombre)
        ).all()
    )


def _obtener_proveedor(
    session: Session, contribuyente_id: int, proveedor_id: int
) -> Proveedor:
    proveedor = session.get(Proveedor, proveedor_id)
    if proveedor is None or proveedor.contribuyente_id != contribuyente_id:
        raise ProveedorNoEncontradoError(
            f"No existe el proveedor {proveedor_id} para el contribuyente "
            f"{contribuyente_id}"
        )
    return proveedor


def crear_documento_soporte(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    datos: DocumentoSoporteCrear,
) -> DocumentoSoporte:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    numero = datos.numero.strip()
    existente = session.exec(
        select(DocumentoSoporte).where(
            DocumentoSoporte.contribuyente_id == contribuyente_id,
            DocumentoSoporte.tipo == datos.tipo,
            DocumentoSoporte.numero == numero,
        )
    ).first()
    if existente is not None:
        raise DocumentoSoporteDuplicadoError(
            f"Ya existe un documento {datos.tipo.value} número {numero}"
        )

    documento = DocumentoSoporte(
        **datos.model_dump(exclude={"numero"}),
        numero=numero,
        contribuyente_id=contribuyente_id,
    )
    session.add(documento)
    session.commit()
    session.refresh(documento)
    return documento


def listar_documentos_soporte(
    session: Session, contador_id: int, contribuyente_id: int
) -> List[DocumentoSoporte]:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    return list(
        session.exec(
            select(DocumentoSoporte)
            .where(DocumentoSoporte.contribuyente_id == contribuyente_id)
            .order_by(DocumentoSoporte.fecha, DocumentoSoporte.id)
        ).all()
    )


def _obtener_documento(
    session: Session, contribuyente_id: int, documento_id: int
) -> DocumentoSoporte:
    documento = session.get(DocumentoSoporte, documento_id)
    if documento is None or documento.contribuyente_id != contribuyente_id:
        raise DocumentoSoporteNoEncontradoError(
            f"No existe el documento soporte {documento_id} para el "
            f"contribuyente {contribuyente_id}"
        )
    return documento


def _movimientos_de_producto(session: Session, producto_id: int) -> List[Movimiento]:
    return list(
        session.exec(
            select(Movimiento)
            .where(Movimiento.producto_id == producto_id)
            .order_by(Movimiento.fecha, Movimiento.id)
        ).all()
    )


def _a_costeo(movimiento: Movimiento) -> costeo.MovimientoCosteo:
    return costeo.MovimientoCosteo(
        fecha=movimiento.fecha,
        orden=float(movimiento.id) if movimiento.id is not None else float("inf"),
        tipo=movimiento.tipo,
        cantidad=movimiento.cantidad,
        valor_unitario=movimiento.valor_unitario,
        movimiento_id=movimiento.id,
        periodo_fiscal_id=movimiento.periodo_fiscal_id,
    )


def registrar_movimiento(
    session: Session, contador_id: int, contribuyente_id: int, datos: MovimientoCrear
) -> Movimiento:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)

    producto = obtener_producto(session, contador_id, contribuyente_id, datos.producto_id)
    if not producto.activo:
        raise ProductoInactivoError(
            f"El producto {producto.codigo} está inactivo: no admite movimientos"
        )

    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, datos.periodo_fiscal_id
    )
    if periodo.estado == EstadoPeriodo.CERRADO:
        raise PeriodoFiscalCerradoError(
            f"El periodo fiscal {periodo.anio_gravable} está cerrado: no admite "
            "nuevos movimientos"
        )
    if datos.fecha.year != periodo.anio_gravable:
        raise MovimientoInvalidoError(
            f"La fecha {datos.fecha.isoformat()} no corresponde al año gravable "
            f"{periodo.anio_gravable} del periodo fiscal"
        )

    _obtener_documento(session, contribuyente_id, datos.documento_soporte_id)

    if datos.proveedor_id is not None:
        if datos.tipo == TipoMovimiento.SALIDA:
            raise MovimientoInvalidoError(
                "Una salida no se asocia a un proveedor: el proveedor solo "
                "aplica a entradas (compras)"
            )
        _obtener_proveedor(session, contribuyente_id, datos.proveedor_id)

    movimiento = Movimiento(**datos.model_dump(), contribuyente_id=contribuyente_id)

    historico = [_a_costeo(m) for m in _movimientos_de_producto(session, producto.id)]
    stock_final = costeo.validar_stock(historico + [_a_costeo(movimiento)])

    producto.stock_actual = stock_final
    session.add(movimiento)
    session.add(producto)
    session.commit()
    session.refresh(movimiento)
    return movimiento


def listar_movimientos(
    session: Session,
    contador_id: int,
    contribuyente_id: int,
    producto_id: Optional[int] = None,
    periodo_fiscal_id: Optional[int] = None,
    tipo: Optional[TipoMovimiento] = None,
) -> List[Movimiento]:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    consulta = select(Movimiento).where(Movimiento.contribuyente_id == contribuyente_id)
    if producto_id is not None:
        consulta = consulta.where(Movimiento.producto_id == producto_id)
    if periodo_fiscal_id is not None:
        consulta = consulta.where(Movimiento.periodo_fiscal_id == periodo_fiscal_id)
    if tipo is not None:
        consulta = consulta.where(Movimiento.tipo == tipo)
    return list(session.exec(consulta.order_by(Movimiento.fecha, Movimiento.id)).all())


def obtener_kardex(
    session: Session, contador_id: int, contribuyente_id: int, producto_id: int
) -> Kardex:
    producto = obtener_producto(session, contador_id, contribuyente_id, producto_id)
    calculadas = costeo.calcular_kardex(
        producto.metodo_costeo,
        [_a_costeo(m) for m in _movimientos_de_producto(session, producto.id)],
    )
    lineas = [c.linea for c in calculadas]
    return Kardex(
        producto_id=producto.id,
        codigo=producto.codigo,
        nombre=producto.nombre,
        metodo_costeo=producto.metodo_costeo,
        lineas=lineas,
        saldo_cantidad=lineas[-1].saldo_cantidad if lineas else 0.0,
        saldo_valor=lineas[-1].saldo_valor if lineas else 0.0,
    )


def kardex_por_periodo(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> List[KardexProductoPeriodo]:
    obtener_contribuyente_con_inventario(session, contador_id, contribuyente_id)
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )

    productos = session.exec(
        select(Producto)
        .where(Producto.contribuyente_id == contribuyente_id)
        .order_by(Producto.codigo)
    ).all()

    resultado: List[KardexProductoPeriodo] = []
    for producto in productos:
        movimientos = [
            _a_costeo(m)
            for m in _movimientos_de_producto(session, producto.id)
            if m.fecha.year <= periodo.anio_gravable
        ]
        if not movimientos:
            continue

        calculadas = costeo.calcular_kardex(producto.metodo_costeo, movimientos)
        del_periodo = [c.linea for c in calculadas if c.periodo_fiscal_id == periodo.id]
        anteriores = [c.linea for c in calculadas if c.periodo_fiscal_id != periodo.id]
        saldo_final = calculadas[-1].linea
        if not del_periodo and saldo_final.saldo_cantidad == 0:
            continue

        resultado.append(
            KardexProductoPeriodo(
                producto_id=producto.id,
                codigo=producto.codigo,
                nombre=producto.nombre,
                metodo_costeo=producto.metodo_costeo,
                saldo_inicial_cantidad=anteriores[-1].saldo_cantidad if anteriores else 0.0,
                saldo_inicial_valor=anteriores[-1].saldo_valor if anteriores else 0.0,
                lineas=del_periodo,
                saldo_final_cantidad=saldo_final.saldo_cantidad,
                saldo_final_valor=saldo_final.saldo_valor,
            )
        )
    return resultado


def calcular_costo_ventas(
    session: Session, contador_id: int, contribuyente_id: int, periodo_fiscal_id: int
) -> CostoVentasPeriodo:
    periodo = obtener_periodo_fiscal(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    )
    resultado: List[CostoVentasProducto] = []
    for kardex in kardex_por_periodo(
        session, contador_id, contribuyente_id, periodo_fiscal_id
    ):
        salidas = [l for l in kardex.lineas if l.tipo == TipoMovimiento.SALIDA]
        # Las sumas se hacen en Decimal: sumar cientos de líneas en binario
        # acumula un error de centavos que termina en la declaración.
        ingresos_d = sum(
            (costeo._d(l.cantidad) * costeo._d(l.precio_venta_unitario or 0)
             for l in salidas),
            costeo.CERO,
        )
        costo_d = sum((costeo._d(l.costo_total) for l in salidas), costeo.CERO)
        ingresos = costeo._pesos(ingresos_d)
        costo = costeo._pesos(costo_d)
        resultado.append(
            CostoVentasProducto(
                producto_id=kardex.producto_id,
                codigo=kardex.codigo,
                nombre=kardex.nombre,
                metodo_costeo=kardex.metodo_costeo,
                cantidad_vendida=sum(l.cantidad for l in salidas),
                ingresos_ventas=ingresos,
                costo_ventas=costo,
                utilidad_bruta=costeo._pesos(ingresos_d - costo_d),
                saldo_final_cantidad=kardex.saldo_final_cantidad,
                saldo_final_valor=kardex.saldo_final_valor,
            )
        )

    total_ingresos_d = sum((costeo._d(p.ingresos_ventas) for p in resultado), costeo.CERO)
    total_costo_d = sum((costeo._d(p.costo_ventas) for p in resultado), costeo.CERO)
    total_ingresos = costeo._pesos(total_ingresos_d)
    total_costo = costeo._pesos(total_costo_d)
    return CostoVentasPeriodo(
        contribuyente_id=contribuyente_id,
        periodo_fiscal_id=periodo.id,
        anio_gravable=periodo.anio_gravable,
        productos=resultado,
        total_ingresos_ventas=total_ingresos,
        total_costo_ventas=total_costo,
        total_utilidad_bruta=costeo._pesos(total_ingresos_d - total_costo_d),
        total_inventario_final=costeo._pesos(
            sum((costeo._d(p.saldo_final_valor) for p in resultado), costeo.CERO)
        ),
    )
