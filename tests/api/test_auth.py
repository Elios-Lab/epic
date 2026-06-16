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



def test_expired_token_is_rejected():
    """A token past its exp claim must be rejected by decode and by the API."""
    import pytest as _pytest

    from epic_core.kernel.auth import create_access_token, decode_access_token
    from epic_core.kernel.config import Settings
    from epic_core.kernel.exceptions import InvalidCredentialsError

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        secret_key="test-secret-key-32-characters-xx",
        access_token_expire_minutes=-1,  # already expired at creation
    )
    token = create_access_token({"sub": "x", "username": "u", "role": "PARTICIPANT"}, settings)

    with _pytest.raises(InvalidCredentialsError):
        decode_access_token(token, settings)


def test_expired_token_returns_401_from_api(client):
    from epic_core.kernel.auth import create_access_token
    from epic_core.kernel.config import Settings

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        secret_key="test-secret-key-32-characters-xx",  # same secret as the test app
        access_token_expire_minutes=-1,
    )
    token = create_access_token({"sub": "x", "username": "u", "role": "PARTICIPANT"}, settings)

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
