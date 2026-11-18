"""Reinicio de los datos demo.

Solo se monta con DEMO_RESET_TOKEN definido. No toca otros contadores.

    POST /demo/reiniciar
    X-Demo-Token: <DEMO_RESET_TOKEN>
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
