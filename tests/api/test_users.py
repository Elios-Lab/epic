def test_create_user_returns_201_and_user_fields(client, admin_headers):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "student1",
            "email": "student@example.com",
            "password": "correct-password",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["username"] == "student1"
    assert body["email"] == "student@example.com"
    assert body["role"] == "PARTICIPANT"
    assert body["status"] == "ACTIVE"
    assert body["is_active"] is True   # backward-compat shim
    assert body["created_at"]


def test_create_user_with_profile_fields(client, admin_headers):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "student2",
            "email": "student2@example.com",
            "password": "correct-password",
            "first_name": "Alice",
            "last_name": "Smith",
            "phone_number": "+39012345678",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["first_name"] == "Alice"
    assert body["last_name"] == "Smith"
    assert body["phone_number"] == "+39012345678"


def test_create_user_response_excludes_password_fields(client, admin_headers):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "student1",
            "email": "student@example.com",
            "password": "correct-password",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert "password" not in body
    assert "password_hash" not in body


def test_create_user_duplicate_username_returns_409(
    client, registered_user, admin_headers
):
    response = client.post(
        "/api/v1/users",
        json={
            "username": registered_user["username"],
            "email": "other@example.com",
            "password": "correct-password",
        },
        headers=admin_headers,
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "REGISTRATION_ERROR"
    assert body["error"]["message"]


def test_create_user_duplicate_email_returns_409(
    client, registered_user, admin_headers
):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "other",
            "email": registered_user["email"],
            "password": "correct-password",
        },
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REGISTRATION_ERROR"


def test_list_users_as_admin_returns_list(client, admin_headers, registered_user):
    response = client.get("/api/v1/users", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    user_ids = {user["id"] for user in body["users"]}
    assert registered_user["id"] in user_ids


def test_get_user_as_admin_returns_user(client, admin_headers, registered_user):
    response = client.get(f"/api/v1/users/{registered_user['id']}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["id"] == registered_user["id"]


def test_patch_user_as_admin_changes_role(client, admin_headers, registered_user):
    response = client.patch(
        f"/api/v1/users/{registered_user['id']}",
        json={"role": "ORGANIZER"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ORGANIZER"


def test_patch_user_as_admin_suspends_user(client, admin_headers, registered_user):
    response = client.patch(
        f"/api/v1/users/{registered_user['id']}",
        json={"status": "SUSPENDED"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUSPENDED"
    assert body["is_active"] is False


def test_suspended_user_cannot_login(client, admin_headers, registered_user):
    client.patch(
        f"/api/v1/users/{registered_user['id']}",
        json={"status": "SUSPENDED"},
        headers=admin_headers,
    )

    login = client.post(
        "/api/v1/auth/login",
        json={"username": registered_user["username"], "password": "correct-password"},
    )
    assert login.status_code == 401


def test_delete_user_as_admin_soft_deletes_user(client, admin_headers, registered_user):
    response = client.delete(
        f"/api/v1/users/{registered_user['id']}",
        headers=admin_headers,
    )

    assert response.status_code == 204
    get_response = client.get(
        f"/api/v1/users/{registered_user['id']}",
        headers=admin_headers,
    )
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "DELETED"
    assert get_response.json()["is_active"] is False


def test_user_management_as_non_admin_returns_403(client, auth_headers, registered_user):
    list_response = client.get("/api/v1/users", headers=auth_headers)
    get_response = client.get(
        f"/api/v1/users/{registered_user['id']}",
        headers=auth_headers,
    )
    patch_response = client.patch(
        f"/api/v1/users/{registered_user['id']}",
        json={"role": "ORGANIZER"},
        headers=auth_headers,
    )
    delete_response = client.delete(
        f"/api/v1/users/{registered_user['id']}",
        headers=auth_headers,
    )

    assert list_response.status_code == 403
    assert get_response.status_code == 403
    assert patch_response.status_code == 403
    assert delete_response.status_code == 403
