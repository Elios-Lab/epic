from datetime import datetime, timedelta, timezone


def contest_payload(name: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "name": name,
        "description": "Registration test contest",
        "visibility": "PUBLIC",
        "twin_id": "mechanical_system",
        "scenario_id": "normal_operation",
        "sampling_rate_hz": 20.0,
        "start_date": now.isoformat(),
        "end_date": (now + timedelta(seconds=1)).isoformat(),
    }


def create_contest(client, admin_headers, name: str, status: str = "DRAFT") -> dict:
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(name),
        headers=admin_headers,
    )
    assert response.status_code == 201
    contest = response.json()
    if status != "DRAFT":
        patch_response = client.patch(
            f"/api/v1/contests/{contest['id']}",
            json={"status": status},
            headers=admin_headers,
        )
        assert patch_response.status_code == 200
        contest = patch_response.json()
    return contest


def register_for_contest(client, auth_headers, contest_id: str):
    return client.post(
        "/api/v1/contest-registrations",
        json={"contest_id": contest_id},
        headers=auth_headers,
    )


def test_post_registers_participant_in_scheduled_contest(
    client, admin_headers, auth_headers, registered_user
):
    contest = create_contest(client, admin_headers, "Scheduled registration", "SCHEDULED")

    response = register_for_contest(client, auth_headers, contest["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["contest_id"] == contest["id"]
    assert body["user_id"] == registered_user["id"]
    assert body["status"] == "REGISTERED"


def test_post_registers_participant_in_active_contest(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers, "Active registration", "ACTIVE")

    response = register_for_contest(client, auth_headers, contest["id"])

    assert response.status_code == 201
    assert response.json()["status"] == "REGISTERED"


def test_post_on_draft_contest_returns_409(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers, "Draft registration")

    response = register_for_contest(client, auth_headers, contest["id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REGISTRATION_ERROR"


def test_post_duplicate_registration_returns_409(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers, "Duplicate registration", "SCHEDULED")
    first_response = register_for_contest(client, auth_headers, contest["id"])
    assert first_response.status_code == 201

    response = register_for_contest(client, auth_headers, contest["id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REGISTRATION_ERROR"


def test_post_on_nonexistent_contest_returns_404(client, auth_headers):
    response = register_for_contest(
        client,
        auth_headers,
        "00000000-0000-0000-0000-000000000001",
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONTEST_NOT_FOUND"


def test_get_returns_only_authenticated_users_registrations(
    client, admin_headers, auth_headers
):
    own_contest = create_contest(client, admin_headers, "Own registration", "SCHEDULED")
    other_contest = create_contest(
        client, admin_headers, "Other registration", "SCHEDULED"
    )
    own_registration = register_for_contest(client, auth_headers, own_contest["id"])
    assert own_registration.status_code == 201

    other_user_response = client.post(
        "/api/v1/users",
        json={
            "username": "student2",
            "email": "student2@example.com",
            "password": "other-password",
        },
    )
    assert other_user_response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "student2", "password": "other-password"},
    )
    assert login_response.status_code == 200
    other_headers = {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }
    other_registration = register_for_contest(
        client, other_headers, other_contest["id"]
    )
    assert other_registration.status_code == 201

    response = client.get("/api/v1/contest-registrations", headers=auth_headers)

    assert response.status_code == 200
    registrations = response.json()["registrations"]
    registration_ids = {registration["registration_id"] for registration in registrations}
    assert own_registration.json()["registration_id"] in registration_ids
    assert other_registration.json()["registration_id"] not in registration_ids


def test_delete_withdraws_registration(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers, "Withdraw registration", "SCHEDULED")
    registration_response = register_for_contest(client, auth_headers, contest["id"])
    assert registration_response.status_code == 201

    response = client.delete(
        f"/api/v1/contest-registrations/{registration_response.json()['registration_id']}",
        headers=auth_headers,
    )

    assert response.status_code == 204


def test_delete_already_withdrawn_registration_returns_409(
    client, admin_headers, auth_headers
):
    contest = create_contest(
        client, admin_headers, "Already withdrawn registration", "SCHEDULED"
    )
    registration_response = register_for_contest(client, auth_headers, contest["id"])
    assert registration_response.status_code == 201
    registration_id = registration_response.json()["registration_id"]
    first_delete = client.delete(
        f"/api/v1/contest-registrations/{registration_id}",
        headers=auth_headers,
    )
    assert first_delete.status_code == 204

    response = client.delete(
        f"/api/v1/contest-registrations/{registration_id}",
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REGISTRATION_ERROR"
