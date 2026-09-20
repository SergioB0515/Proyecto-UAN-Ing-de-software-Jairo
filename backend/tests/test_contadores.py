def test_registro_exitoso(client):
    respuesta = client.post(
        "/contadores/registro",
        json={
            "nombre": "Ana Pérez",
            "email": "ana@example.com",
            "contrasena": "claveSegura123",
        },
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["email"] == "ana@example.com"
    assert cuerpo["nombre"] == "Ana Pérez"
    # La contraseña y su hash nunca deben salir en la respuesta.
    assert "contrasena" not in cuerpo
    assert "hash_contrasena" not in cuerpo


def test_registro_con_email_duplicado_falla(client):
    datos = {
        "nombre": "Ana Pérez",
        "email": "duplicado@example.com",
        "contrasena": "claveSegura123",
    }
    primera = client.post("/contadores/registro", json=datos)
    segunda = client.post("/contadores/registro", json=datos)

    assert primera.status_code == 201
    assert segunda.status_code == 409


def test_registro_con_contrasena_muy_corta_falla(client):
    respuesta = client.post(
        "/contadores/registro",
        json={"nombre": "Ana", "email": "corta@example.com", "contrasena": "123"},
    )
    assert respuesta.status_code == 422


def test_login_exitoso_devuelve_token(client):
    client.post(
        "/contadores/registro",
        json={
            "nombre": "Luis Gómez",
            "email": "luis@example.com",
            "contrasena": "otraClave456",
        },
    )

    respuesta = client.post(
        "/contadores/login",
        data={"username": "luis@example.com", "password": "otraClave456"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert isinstance(cuerpo["access_token"], str) and len(cuerpo["access_token"]) > 0


def test_login_con_contrasena_incorrecta_falla(client):
    client.post(
        "/contadores/registro",
        json={
            "nombre": "Marta Ruiz",
            "email": "marta@example.com",
            "contrasena": "claveCorrecta1",
        },
    )

    respuesta = client.post(
        "/contadores/login",
        data={"username": "marta@example.com", "password": "claveIncorrecta"},
    )

    assert respuesta.status_code == 401


def test_login_con_email_inexistente_falla(client):
    respuesta = client.post(
        "/contadores/login",
        data={"username": "no-existe@example.com", "password": "loQueSea123"},
    )
    assert respuesta.status_code == 401


def test_endpoint_protegido_sin_token_falla(client):
    respuesta = client.get("/contadores/yo")
    assert respuesta.status_code == 401


def test_endpoint_protegido_con_token_invalido_falla(client):
    respuesta = client.get(
        "/contadores/yo", headers={"Authorization": "Bearer un-token-inventado"}
    )
    assert respuesta.status_code == 401


def test_endpoint_protegido_con_token_valido_funciona(client):
    client.post(
        "/contadores/registro",
        json={
            "nombre": "Carlos Díaz",
            "email": "carlos@example.com",
            "contrasena": "claveValida789",
        },
    )
    login = client.post(
        "/contadores/login",
        data={"username": "carlos@example.com", "password": "claveValida789"},
    )
    token = login.json()["access_token"]

    respuesta = client.get(
        "/contadores/yo", headers={"Authorization": f"Bearer {token}"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == "carlos@example.com"
