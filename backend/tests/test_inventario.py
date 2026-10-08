def _crear_contador_y_token(client, email: str) -> str:
    client.post(
        "/contadores/registro",
        json={"nombre": "Contador de prueba", "email": email, "contrasena": "claveDePrueba1"},
    )
    login = client.post(
        "/contadores/login", data={"username": email, "password": "claveDePrueba1"}
    )
    return login.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _crear_contribuyente(client, token: str, tipo: str) -> int:
    respuesta = client.post(
        "/contribuyentes",
        json={"nombre": f"Contribuyente {tipo}", "rut": "3000000000", "tipo_contribuyente": tipo},
        headers=_headers(token),
    )
    return respuesta.json()["id"]


def _producto(categoria_id=None, **extra) -> dict:
    datos = {
        "codigo": "P-001",
        "nombre": "Producto de prueba",
        "clasificacion_iva": "GRAVADO",
        "metodo_costeo": "PEPS",
        "categoria_id": categoria_id,
    }
    datos.update(extra)
    return datos


def test_crear_categoria_y_producto(client):
    token = _crear_contador_y_token(client, "inventario1@example.com")
    cid = _crear_contribuyente(client, token, "INDEPENDIENTE")

    categoria = client.post(
        f"/contribuyentes/{cid}/categorias",
        json={"nombre": "Producto terminado"},
        headers=_headers(token),
    )
    assert categoria.status_code == 201

    producto = client.post(
        f"/contribuyentes/{cid}/productos",
        json=_producto(categoria.json()["id"]),
        headers=_headers(token),
    )
    assert producto.status_code == 201
    assert producto.json()["stock_actual"] == 0
    assert producto.json()["activo"] is True

    listado = client.get(f"/contribuyentes/{cid}/productos", headers=_headers(token))
    assert len(listado.json()) == 1


def test_asalariado_no_tiene_inventario(client):
    token = _crear_contador_y_token(client, "inventario2@example.com")
    cid = _crear_contribuyente(client, token, "ASALARIADO")

    respuesta = client.post(
        f"/contribuyentes/{cid}/categorias",
        json={"nombre": "No aplica"},
        headers=_headers(token),
    )
    assert respuesta.status_code == 409


def test_producto_exige_clasificacion_iva_y_metodo_costeo(client):
    token = _crear_contador_y_token(client, "inventario3@example.com")
    cid = _crear_contribuyente(client, token, "MIXTO")

    datos = _producto()
    del datos["clasificacion_iva"]
    respuesta = client.post(
        f"/contribuyentes/{cid}/productos", json=datos, headers=_headers(token)
    )
    assert respuesta.status_code == 422

    respuesta = client.post(
        f"/contribuyentes/{cid}/productos",
        json=_producto(metodo_costeo="UEPS"),
        headers=_headers(token),
    )
    assert respuesta.status_code == 422


def test_no_se_elimina_categoria_con_productos_activos(client):
    token = _crear_contador_y_token(client, "inventario4@example.com")
    cid = _crear_contribuyente(client, token, "INDEPENDIENTE")
    categoria_id = client.post(
        f"/contribuyentes/{cid}/categorias",
        json={"nombre": "Materia prima"},
        headers=_headers(token),
    ).json()["id"]
    producto_id = client.post(
        f"/contribuyentes/{cid}/productos",
        json=_producto(categoria_id),
        headers=_headers(token),
    ).json()["id"]

    respuesta = client.delete(
        f"/contribuyentes/{cid}/categorias/{categoria_id}", headers=_headers(token)
    )
    assert respuesta.status_code == 409

    # Desactivado el producto, la categoría ya se puede eliminar y el
    # producto sigue existiendo, sin categoría (agregación).
    client.patch(
        f"/contribuyentes/{cid}/productos/{producto_id}",
        json={"activo": False},
        headers=_headers(token),
    )
    respuesta = client.delete(
        f"/contribuyentes/{cid}/categorias/{categoria_id}", headers=_headers(token)
    )
    assert respuesta.status_code == 204

    producto = client.get(
        f"/contribuyentes/{cid}/productos/{producto_id}", headers=_headers(token)
    )
    assert producto.status_code == 200
    assert producto.json()["categoria_id"] is None


def test_producto_con_categoria_de_otro_contribuyente_falla(client):
    token = _crear_contador_y_token(client, "inventario5@example.com")
    cid_a = _crear_contribuyente(client, token, "INDEPENDIENTE")
    cid_b = _crear_contribuyente(client, token, "INDEPENDIENTE")
    categoria_de_a = client.post(
        f"/contribuyentes/{cid_a}/categorias",
        json={"nombre": "De A"},
        headers=_headers(token),
    ).json()["id"]

    respuesta = client.post(
        f"/contribuyentes/{cid_b}/productos",
        json=_producto(categoria_de_a),
        headers=_headers(token),
    )
    assert respuesta.status_code == 404


def test_un_contador_no_ve_inventario_de_otro(client):
    token_a = _crear_contador_y_token(client, "inventario6a@example.com")
    token_b = _crear_contador_y_token(client, "inventario6b@example.com")
    cid = _crear_contribuyente(client, token_a, "INDEPENDIENTE")

    respuesta = client.get(f"/contribuyentes/{cid}/productos", headers=_headers(token_b))
    assert respuesta.status_code == 404
