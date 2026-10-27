from datetime import date, datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import computed_field
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

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
    cantidad: float = Field(gt=0)
    valor_unitario: float = Field(gt=0)


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
    def valor_total(self) -> float:
        return round(self.cantidad * self.valor_unitario, 2)


class LineaKardex(SQLModel):
    movimiento_id: int
    fecha: date
    tipo: TipoMovimiento
    cantidad: float
    costo_unitario: float
    costo_total: float
    saldo_cantidad: float
    saldo_valor: float
    precio_venta_unitario: Optional[float] = None


class Kardex(SQLModel):
    producto_id: int
    codigo: str
    nombre: str
    metodo_costeo: MetodoCosteo
    lineas: List[LineaKardex]
    saldo_cantidad: float
    saldo_valor: float


class KardexProductoPeriodo(SQLModel):
    producto_id: int
    codigo: str
    nombre: str
    metodo_costeo: MetodoCosteo
    saldo_inicial_cantidad: float
    saldo_inicial_valor: float
    lineas: List[LineaKardex]
    saldo_final_cantidad: float
    saldo_final_valor: float


class CostoVentasProducto(SQLModel):
    producto_id: int
    codigo: str
    nombre: str
    metodo_costeo: MetodoCosteo
    cantidad_vendida: float
    ingresos_ventas: float
    costo_ventas: float
    utilidad_bruta: float
    saldo_final_cantidad: float
    saldo_final_valor: float


class CostoVentasPeriodo(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    anio_gravable: int
    productos: List[CostoVentasProducto]
    total_ingresos_ventas: float
    total_costo_ventas: float
    total_utilidad_bruta: float
    total_inventario_final: float
