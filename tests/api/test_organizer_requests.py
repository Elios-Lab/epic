"""Tests for the organizer self-registration and admin approval workflow."""

REGISTER_URL = "/api/v1/organizer-requests"


def _valid_payload(**overrides):
    base = {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
        "phone_number": "+39012345678",
        "password": "secure-password-123",
    }
    base.update(overrides)
    return base


# ── Self-registration ─────────────────────────────────────────────────────────

def test_organizer_self_registration_returns_201(client):
    response = client.post(REGISTER_URL, json=_valid_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["first_name"] == "Alice"
    assert body["last_name"] == "Smith"
    assert body["email"] == "alice@example.com"
    assert body["status"] == "PENDING"
    assert body["created_at"]


def test_organizer_self_registration_excludes_password(client):
    response = client.post(REGISTER_URL, json=_valid_payload())

    body = response.json()
    assert "password" not in body
    assert "password_hash" not in body


def test_organizer_self_registration_notifies_admin(client, collecting_notifications):
    client.post(REGISTER_URL, json=_valid_payload())

    assert len(collecting_notifications.organizer_requests_received) == 1
    notification = collecting_notifications.organizer_requests_received[0]
    assert notification["requester_email"] == "alice@example.com"


def test_organizer_self_registration_duplicate_email_returns_409(client):
    client.post(REGISTER_URL, json=_valid_payload())
    response = client.post(REGISTER_URL, json=_valid_payload())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REGISTRATION_ERROR"


def test_organizer_self_registration_no_auth_required(client):
    """Public endpoint — no Authorization header needed."""
    response = client.post(REGISTER_URL, json=_valid_payload())
    assert response.status_code == 201


# ── Admin listing ─────────────────────────────────────────────────────────────

def test_list_organizer_requests_as_admin(client, admin_headers):
    client.post(REGISTER_URL, json=_valid_payload())

    response = client.get(REGISTER_URL, headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(r["email"] == "alice@example.com" for r in body["requests"])


def test_list_organizer_requests_filters_by_status(client, admin_headers):
    client.post(REGISTER_URL, json=_valid_payload())

    pending = client.get(f"{REGISTER_URL}?status=PENDING", headers=admin_headers)
    approved = client.get(f"{REGISTER_URL}?status=APPROVED", headers=admin_headers)

    assert pending.status_code == 200
    assert pending.json()["total"] >= 1
    assert approved.json()["total"] == 0


def test_list_organizer_requests_as_non_admin_returns_403(client, auth_headers):
    response = client.get(REGISTER_URL, headers=auth_headers)
    assert response.status_code == 403


# ── Admin approval ────────────────────────────────────────────────────────────

def test_approve_organizer_request_creates_active_organizer(
    client, admin_headers, collecting_notifications
):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()
    request_id = reg["id"]

    response = client.post(
        f"{REGISTER_URL}/{request_id}/approve",
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "APPROVED"
    assert body["user_id"] is not None


def test_approve_organizer_request_user_can_login(client, admin_headers):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()
    client.post(f"{REGISTER_URL}/{reg['id']}/approve", headers=admin_headers)

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "alice@example.com", "password": "secure-password-123"},
    )

    assert login.status_code == 200
    assert login.json()["access_token"]


def test_approve_organizer_request_sends_notification(
    client, admin_headers, collecting_notifications
):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()
    client.post(f"{REGISTER_URL}/{reg['id']}/approve", headers=admin_headers)

    assert "alice@example.com" in collecting_notifications.organizer_approvals


def test_approve_organizer_request_approved_user_has_organizer_role(
    client, admin_headers
):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()
    approved = client.post(
        f"{REGISTER_URL}/{reg['id']}/approve", headers=admin_headers
    ).json()
    user_id = approved["user_id"]

    user = client.get(f"/api/v1/users/{user_id}", headers=admin_headers).json()
    assert user["role"] == "ORGANIZER"
    assert user["status"] == "ACTIVE"


def test_approve_already_approved_request_returns_409(client, admin_headers):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()
    client.post(f"{REGISTER_URL}/{reg['id']}/approve", headers=admin_headers)
    response = client.post(
        f"{REGISTER_URL}/{reg['id']}/approve", headers=admin_headers
    )

    assert response.status_code == 409


def test_approve_organizer_request_as_non_admin_returns_403(client, auth_headers):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()
    response = client.post(
        f"{REGISTER_URL}/{reg['id']}/approve", headers=auth_headers
    )
    assert response.status_code == 403


# ── Admin rejection ───────────────────────────────────────────────────────────

def test_reject_organizer_request_returns_200(client, admin_headers):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()

    response = client.post(
        f"{REGISTER_URL}/{reg['id']}/reject",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_reject_organizer_request_sends_notification(
    client, admin_headers, collecting_notifications
):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()
    client.post(f"{REGISTER_URL}/{reg['id']}/reject", headers=admin_headers)

    assert "alice@example.com" in collecting_notifications.organizer_rejections


def test_reject_organizer_request_rejected_email_cannot_register_again(
    client, admin_headers
):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()
    client.post(f"{REGISTER_URL}/{reg['id']}/reject", headers=admin_headers)

    # Re-registration with same email should still fail (unique constraint)
    response = client.post(REGISTER_URL, json=_valid_payload())
    assert response.status_code == 409


def test_reject_already_decided_request_returns_409(client, admin_headers):
    reg = client.post(REGISTER_URL, json=_valid_payload()).json()
    client.post(f"{REGISTER_URL}/{reg['id']}/reject", headers=admin_headers)
    response = client.post(
        f"{REGISTER_URL}/{reg['id']}/reject", headers=admin_headers
    )
    assert response.status_code == 409
