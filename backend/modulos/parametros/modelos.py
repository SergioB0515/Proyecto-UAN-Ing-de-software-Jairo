"""UmbralDeclaracion: topes de declaración de renta por año gravable
(UVT y los cinco criterios). Ver documentacion/07-diagrama-clases.md y
documentacion/03-logica-proyecto.md (Proceso 5).

No pertenece a ningún contador ni contribuyente — es un dato de
configuración compartido (documentacion/04-arquitectura.md).
"""
from typing import List

from sqlmodel import Field, SQLModel


class UmbralDeclaracionBase(SQLModel):
    valor_uvt: float = Field(gt=0)
    tope_ingresos_uvt: float = Field(gt=0)
    tope_patrimonio_uvt: float = Field(gt=0)
    tope_consumo_tc_uvt: float = Field(gt=0)
    tope_compras_uvt: float = Field(gt=0)
    tope_movimiento_uvt: float = Field(gt=0)


class UmbralDeclaracion(UmbralDeclaracionBase, table=True):
    __tablename__ = "umbrales_declaracion"

    # El año gravable es la llave primaria: un único umbral vigente por año.
    anio_gravable: int = Field(primary_key=True, ge=2000, le=2100)


class UmbralDeclaracionCrear(UmbralDeclaracionBase):
    anio_gravable: int = Field(ge=2000, le=2100)


class UmbralDeclaracionLeer(UmbralDeclaracionBase):
    anio_gravable: int


# ------------------------------------------------ Clases de resultado (no persisten)
# El resultado de "¿está obligado a declarar?" se calcula al momento de la
# consulta (documentacion/03-logica-proyecto.md, Proceso 5) — no se guarda
# como tabla, para no quedar desactualizado si cambia un tope o un umbral.


class DetalleCriterio(SQLModel):
    criterio: str  # "Ingresos", "Patrimonio", "Consumo TC", "Compras", "Movimiento"
    valor_reportado: float
    umbral: float
    supera_umbral: bool


class ResultadoObligacion(SQLModel):
    contribuyente_id: int
    periodo_fiscal_id: int
    anio_gravable: int
    obligado: bool
    criterios: List[DetalleCriterio]
    advertencia: str = (
        "Este resultado no evalúa el criterio de responsable de IVA "
        "durante el año (no aparece en la información exógena) — "
        "verifícalo aparte. Es una señal de apoyo, no un veredicto legal "
        "completo."
    )
