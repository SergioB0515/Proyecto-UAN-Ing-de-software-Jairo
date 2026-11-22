from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import computed_field
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from core.dinero import campo_cantidad, campo_dinero, redondear_pesos

from ..inventario.modelos import MetodoCosteo


class TipoPersona(str, Enum):
    NATURAL = "NATURAL"
    JURIDICA = "JURIDICA"


class TipoDocumentoSoporte(str, Enum):
    FACTURA = "FACTURA"
    DOCUMENTO_SOPORTE = "DOCUMENTO_SOPORTE"
    NOTA_CREDITO = "NOTA_CREDITO"
    NOTA_DEBITO = "NOTA_DEBITO"
    ACTA = "ACTA"
    OTRO = "OTRO"


class TipoMovimiento(str, Enum):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"


class ProveedorBase(SQLModel):
    nombre: str = Field(min_length=1, max_length=200)
    tipo_persona: TipoPersona
    identificacion: str = Field(min_length=1, max_length=20)


class Proveedor(ProveedorBase, table=True):
    __tablename__ = "proveedores"
    __table_args__ = (UniqueConstraint("contribuyente_id", "identificacion"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)


class ProveedorCrear(ProveedorBase):
    pass


class ProveedorLeer(ProveedorBase):
    id: int
    contribuyente_id: int


class DocumentoSoporteBase(SQLModel):
    tipo: TipoDocumentoSoporte
    numero: str = Field(min_length=1, max_length=60)
    fecha: date
    descripcion: Optional[str] = Field(default=None, max_length=300)


class DocumentoSoporte(DocumentoSoporteBase, table=True):
    __tablename__ = "documentos_soporte"
    __table_args__ = (UniqueConstraint("contribuyente_id", "tipo", "numero"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)


class DocumentoSoporteCrear(DocumentoSoporteBase):
    pass


class DocumentoSoporteLeer(DocumentoSoporteBase):
    id: int
    contribuyente_id: int


class MovimientoBase(SQLModel):
    tipo: TipoMovimiento
    producto_id: int = Field(foreign_key="productos.id", index=True)
    periodo_fiscal_id: int = Field(foreign_key="periodos_fiscales.id", index=True)
    documento_soporte_id: int = Field(foreign_key="documentos_soporte.id", index=True)
    proveedor_id: Optional[int] = Field(default=None, foreign_key="proveedores.id")
    fecha: date
    cantidad: Decimal = campo_cantidad(gt=0)
    valor_unitario: Decimal = campo_dinero(gt=0)


class Movimiento(MovimientoBase, table=True):
    __tablename__ = "movimientos"

    id: Optional[int] = Field(default=None, primary_key=True)
    contribuyente_id: int = Field(foreign_key="contribuyentes.id", index=True)
    creado_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class MovimientoCrear(MovimientoBase):
    pass


class MovimientoLeer(MovimientoBase):
    id: int
    contribuyente_id: int
    creado_en: datetime

    @computed_field
    @property
    def valor_total(self) -> Decimal:
        # cantidad trae tres decimales y valor_unitario dos, así que el
        # producto trae cinco: hay que redondearlo a centavos y no dejar que
        # lo recorte quien lo muestre.
        return redondear_pesos(self.cantidad * self.valor_unitario)


class LineaKardex(SQLModel):
    movimiento_id: int
    fecha: date
    tipo: TipoMovimiento
    cantidad: Decimal
    costo_unitario: Decimal
    costo_total: Decimal
    saldo_cantidad: Decimal
    saldo_valor: Decimal
    precio_venta_unitario: Optional[Decimal] = None


class Kardex(SQLModel):
    producto_id: int
    codigo: str
    nombre: str
    metodo_costeo: MetodoCosteo
    lineas: List[LineaKardex]
    saldo_cantidad: Decimal
    saldo_valor: Decimal


class KardexProductoPeriodo(SQLModel):
    producto_id: int
    codigo: str
    nombre: str
    metodo_costeo: MetodoCosteo
    saldo_inicial_cantidad: Decimal
    saldo_inicial_valor: Decimal
    lineas: List[LineaKardex]
    saldo_final_cantidad: Decimal
    saldo_final_valor: Decimal


class CostoVentasProducto(SQLModel):
    producto_id: int
    codigo: str
    nombre: str
    metodo_costeo: MetodoCosteo
    cantidad_vendida: Decimal
    ingresos_ventas: Decimal
    costo_ventas: Decimal
    utilidad_bruta: Decimal
    saldo_final_cantidad: Decimal
    saldo_final_valor: Decimal


class CostoVentasPeriodo(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    anio_gravable: int
    productos: List[CostoVentasProducto]
    total_ingresos_ventas: Decimal
    total_costo_ventas: Decimal
    total_utilidad_bruta: Decimal
    total_inventario_final: Decimal
