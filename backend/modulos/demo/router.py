"""Reinicio de los datos de demostración desde la propia aplicación.

Existe por una sola razón: si algo se daña a mitad de una sustentación (un
registro borrado por error, un periodo cerrado sin querer), devolver la base a
su estado inicial debe tomar segundos y no obligar a abrir una terminal.

El router SOLO se monta si la variable de entorno ``DEMO_RESET_TOKEN`` está
definida. En un despliegue que no sea de demostración, simplemente no se
define y el endpoint no existe.

    POST /demo/reiniciar
    X-Demo-Token: <el valor de DEMO_RESET_TOKEN>

Borra los datos del contador demo y los vuelve a crear. No toca ningún otro
contador registrado en la base.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlmodel import Session

from database import obtener_sesion

router = APIRouter(prefix="/demo", tags=["demo"])

TOKEN = os.getenv("DEMO_RESET_TOKEN", "")


def _verificar_token(x_demo_token: str = Header(default="")) -> None:
    if not TOKEN or not secrets.compare_digest(x_demo_token, TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de demostración inválido",
        )


@router.post(
    "/reiniciar",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(_verificar_token)],
    summary="Devuelve los datos de demostración a su estado inicial",
)
def reiniciar(session: Session = Depends(obtener_sesion)) -> dict:
    import semilla_demo

    borrados = semilla_demo.borrar_demo(session)
    semilla_demo.cargar_demo(session)
    return {
        "reiniciado": True,
        "habia_datos_previos": borrados,
        "usuario": semilla_demo.EMAIL_DEMO,
        "anio_gravable": semilla_demo.ANIO,
    }
