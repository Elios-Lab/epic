def test_create_user_returns_201_and_user_fields(client):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "student1",
            "email": "student@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["username"] == "student1"
    assert body["email"] == "student@example.com"
    assert body["role"] == "PARTICIPANT"
    assert body["is_active"] is True
    assert body["created_at"]


def test_create_user_response_excludes_password_fields(client):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "student1",
            "email": "student@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert "password" not in body
    assert "password_hash" not in body


def test_create_user_duplicate_username_returns_409(client, registered_user):
    response = client.post(
        "/api/v1/users",
        json={
            "username": registered_user["username"],
            "email": "other@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "REGISTRATION_ERROR"
    assert body["error"]["message"]


def test_create_user_duplicate_email_returns_409(client, registered_user):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "other",
            "email": registered_user["email"],
            "password": "correct-password",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REGISTRATION_ERROR"

