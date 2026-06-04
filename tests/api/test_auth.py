def test_login_with_correct_credentials_returns_token(client, registered_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": registered_user["username"], "password": "correct-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_login_with_wrong_password_returns_401(client, registered_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": registered_user["username"], "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_login_with_unknown_username_returns_401(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "unknown", "password": "correct-password"},
    )

    assert response.status_code == 401


def test_get_me_with_valid_token_returns_current_user(client, registered_user, auth_headers):
    response = client.get("/api/v1/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["username"] == registered_user["username"]


def test_get_me_without_token_returns_401(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_get_me_with_malformed_token_returns_401(client):
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer malformed-token"}
    )

    assert response.status_code == 401

