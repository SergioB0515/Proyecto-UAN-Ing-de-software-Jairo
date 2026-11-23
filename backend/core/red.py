"""Dirección de quien hace la petición.

Es la única función del backend que decide qué IP queda en la bitácora, en
los intentos de acceso y en el respaldo de la autorización del portal. Por
eso la confianza en `X-Forwarded-For` se decide aquí, y no en las banderas
del servidor.

## Por qué no se le deja a uvicorn

Con `--proxy-headers --forwarded-allow-ips='*'`, uvicorn reemplaza
`request.client.host` por la **primera** dirección de `X-Forwarded-For`, que
es la que escribe el cliente. Un proxy no borra esa cabecera: le agrega al
final la dirección de quien le habló. Así, quien manda
`X-Forwarded-For: 1.2.3.4` queda registrado como `1.2.3.4` aunque el proxy
haya anotado detrás la dirección real.

## Cómo se decide

`PROXIES_CONFIABLES` dice cuántos proxies propios hay delante de la
aplicación. Cada uno agrega una entrada al final de la cabecera, así que la
dirección del cliente es la N-ésima contando desde la derecha. Lo que está
más a la izquierda lo escribió alguien que no controlamos y no se lee.

- `0` (por omisión): no se lee la cabecera. Se registra la dirección de la
  conexión. Es lo correcto cuando nadie está delante, como en desarrollo o
  con `docker compose`.
- `1`: un proxy delante, como el de Render.

Si la cabecera trae menos entradas de las que debería, o la que toca no es
una IP, se registra la dirección de la conexión: mejor la del proxy, que es
verdad, que una que alguien pudo escribir.
"""

import ipaddress
from typing import Optional

from starlette.requests import Request

from core import config


def _direccion_de_conexion(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _entradas_forwarded_for(request: Request) -> list:
    # Puede llegar repetida; el orden de las cabeceras se conserva.
    entradas = []
    for valor in request.headers.getlist("x-forwarded-for"):
        entradas.extend(parte.strip() for parte in valor.split(",") if parte.strip())
    return entradas


def _es_ip(valor: str) -> bool:
    try:
        ipaddress.ip_address(valor)
    except ValueError:
        return False
    return True


def ip_cliente(request: Request) -> Optional[str]:
    conexion = _direccion_de_conexion(request)
    saltos = config.PROXIES_CONFIABLES
    if saltos <= 0:
        return conexion

    entradas = _entradas_forwarded_for(request)
    if len(entradas) < saltos:
        return conexion

    candidata = entradas[-saltos]
    return candidata if _es_ip(candidata) else conexion
