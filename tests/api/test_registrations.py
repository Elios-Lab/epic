from datetime import datetime, timedelta, timezone


def contest_payload(name: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "name": name,
        "description": "Registration test contest",
        "visibility": "PUBLIC",
        "twin_id": "mass_spring_damper",
        "sensor_configs": [{"sensor_id": "position"}],
        "sampling_rate_hz": 20.0,
        "start_date": (now - timedelta(seconds=10)).isoformat(),
        "end_of_observation": (now - timedelta(seconds=2)).isoformat(),
        "prediction_horizon_seconds": 0.1,
        "end_date": (now + timedelta(seconds=30)).isoformat(),
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
            f"/api/v1/contests/{contest['contest_id']}",
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

    response = register_for_contest(client, auth_headers, contest["contest_id"])

    assert response.status_code == 201
    body = response.json()
    assert body["contest_id"] == contest["contest_id"]
    assert body["user_id"] == registered_user["id"]
    assert body["status"] == "REGISTERED"


def test_post_registers_participant_in_active_contest(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers, "Active registration", "ACTIVE")

    response = register_for_contest(client, auth_headers, contest["contest_id"])

    assert response.status_code == 201
    assert response.json()["status"] == "REGISTERED"


def test_post_on_draft_contest_returns_409(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers, "Draft registration")

    response = register_for_contest(client, auth_headers, contest["contest_id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REGISTRATION_ERROR"


def test_post_duplicate_registration_returns_409(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers, "Duplicate registration", "SCHEDULED")
    first_response = register_for_contest(client, auth_headers, contest["contest_id"])
    assert first_response.status_code == 201

    response = register_for_contest(client, auth_headers, contest["contest_id"])

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
    own_registration = register_for_contest(client, auth_headers, own_contest["contest_id"])
    assert own_registration.status_code == 201

    other_user_response = client.post(
        "/api/v1/users",
        json={
            "username": "student2",
            "email": "student2@example.com",
            "password": "other-password",
        },
        headers=admin_headers,
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
        client, other_headers, other_contest["contest_id"]
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
    registration_response = register_for_contest(client, auth_headers, contest["contest_id"])
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
    registration_response = register_for_contest(client, auth_headers, contest["contest_id"])
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


def test_organizer_can_filter_registrations_for_own_contest(
    client, organizer_headers, auth_headers, admin_headers
):
    contest = create_contest(
        client, organizer_headers, "Organizer registration filter", "SCHEDULED"
    )
    first_registration = register_for_contest(
        client, auth_headers, contest["contest_id"]
    )
    assert first_registration.status_code == 201

    other_user_response = client.post(
        "/api/v1/users",
        json={
            "username": "registration-filter-user",
            "email": "registration-filter-user@example.com",
            "password": "other-password",
        },
        headers=admin_headers,
    )
    assert other_user_response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "registration-filter-user", "password": "other-password"},
    )
    assert login_response.status_code == 200
    other_headers = {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }
    second_registration = register_for_contest(
        client, other_headers, contest["contest_id"]
    )
    assert second_registration.status_code == 201

    response = client.get(
        "/api/v1/contest-registrations",
        params={"contest_id": contest["contest_id"]},
        headers=organizer_headers,
    )

    assert response.status_code == 200
    registration_ids = {
        registration["registration_id"]
        for registration in response.json()["registrations"]
    }
    assert first_registration.json()["registration_id"] in registration_ids
    assert second_registration.json()["registration_id"] in registration_ids


def test_participant_contest_filter_returns_only_own_registrations(
    client, admin_headers, auth_headers
):
    own_contest = create_contest(
        client, admin_headers, "Participant own registration filter", "SCHEDULED"
    )
    other_contest = create_contest(
        client, admin_headers, "Participant other registration filter", "SCHEDULED"
    )
    own_registration = register_for_contest(
        client, auth_headers, own_contest["contest_id"]
    )
    assert own_registration.status_code == 201

    other_user_response = client.post(
        "/api/v1/users",
        json={
            "username": "participant-filter-user",
            "email": "participant-filter-user@example.com",
            "password": "other-password",
        },
        headers=admin_headers,
    )
    assert other_user_response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "participant-filter-user", "password": "other-password"},
    )
    assert login_response.status_code == 200
    other_headers = {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }
    other_registration = register_for_contest(
        client, other_headers, other_contest["contest_id"]
    )
    assert other_registration.status_code == 201

    response = client.get(
        "/api/v1/contest-registrations",
        params={"contest_id": other_contest["contest_id"]},
        headers=auth_headers,
    )

    assert response.status_code == 200
    registration_ids = {
        registration["registration_id"]
        for registration in response.json()["registrations"]
    }
    assert own_registration.json()["registration_id"] in registration_ids
    assert other_registration.json()["registration_id"] not in registration_ids


# ── Visibility enforcement ────────────────────────────────────────────────────

def _create_restricted_contest(client, admin_headers, name: str, visibility: str) -> dict:
    payload = contest_payload(name)
    payload["visibility"] = visibility
    response = client.post("/api/v1/contests", json=payload, headers=admin_headers)
    assert response.status_code == 201
    contest = response.json()
    patch = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "SCHEDULED"},
        headers=admin_headers,
    )
    assert patch.status_code == 200
    return patch.json()


def test_post_on_invitation_only_contest_without_invitation_returns_409(
    client, admin_headers, auth_headers
):
    """An uninvited participant must not be able to join a restricted contest."""
    contest = _create_restricted_contest(
        client, admin_headers, "Private no invitation", "PRIVATE"
    )

    response = register_for_contest(client, auth_headers, contest["contest_id"])

    assert response.status_code == 409
    assert "invitation" in response.json()["error"]["message"].lower()


def test_post_on_private_contest_without_invitation_returns_409(
    client, admin_headers, auth_headers
):
    contest = _create_restricted_contest(
        client, admin_headers, "Private no invite", "PRIVATE"
    )

    response = register_for_contest(client, auth_headers, contest["contest_id"])

    assert response.status_code == 409


def test_post_on_invitation_only_contest_with_invitation_returns_201(
    client, admin_headers, auth_headers, registered_user
):
    """An existing account whose email was invited may self-register."""
    contest = _create_restricted_contest(
        client, admin_headers, "Private with invitation", "PRIVATE"
    )
    invite = client.post(
        f"/api/v1/contests/{contest['contest_id']}/invitations",
        json={"emails": [registered_user["email"]]},
        headers=admin_headers,
    )
    assert invite.status_code == 201

    response = register_for_contest(client, auth_headers, contest["contest_id"])

    assert response.status_code == 201
    assert response.json()["status"] == "REGISTERED"


def test_admin_can_register_for_restricted_contest_without_invitation(
    client, admin_headers
):
    """Administrators bypass the invitation requirement."""
    contest = _create_restricted_contest(
        client, admin_headers, "Private admin join", "PRIVATE"
    )

    response = client.post(
        "/api/v1/contest-registrations",
        json={"contest_id": contest["contest_id"]},
        headers=admin_headers,
    )

    assert response.status_code == 201


# ── Organizer participant management ──────────────────────────────────────────

def test_withdrawn_participant_can_rejoin(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers, "Rejoin after withdraw", "SCHEDULED")
    first = register_for_contest(client, auth_headers, contest["contest_id"])
    assert first.status_code == 201
    registration_id = first.json()["registration_id"]

    withdraw = client.delete(
        f"/api/v1/contest-registrations/{registration_id}", headers=auth_headers
    )
    assert withdraw.status_code == 204

    rejoin = register_for_contest(client, auth_headers, contest["contest_id"])
    assert rejoin.status_code == 201
    assert rejoin.json()["status"] == "REGISTERED"
    # Same registration row, reactivated — not a duplicate.
    assert rejoin.json()["registration_id"] == registration_id


def test_organizer_removal_bans_participant(
    client, admin_headers, organizer_headers, auth_headers, registered_user
):
    """A removal by the contest owner is an exclusion: the participant cannot rejoin."""
    payload = contest_payload("Removal contest")
    response = client.post("/api/v1/contests", json=payload, headers=organizer_headers)
    assert response.status_code == 201
    contest = response.json()
    client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "SCHEDULED"},
        headers=organizer_headers,
    )
    registration = register_for_contest(client, auth_headers, contest["contest_id"])
    assert registration.status_code == 201
    registration_id = registration.json()["registration_id"]

    # The organizer removes the participant.
    removal = client.delete(
        f"/api/v1/contest-registrations/{registration_id}", headers=organizer_headers
    )
    assert removal.status_code == 204

    # The participant cannot rejoin.
    rejoin = register_for_contest(client, auth_headers, contest["contest_id"])
    assert rejoin.status_code == 409
    assert "removed" in rejoin.json()["error"]["message"].lower()


def test_other_organizer_cannot_remove_participant(
    client, admin_headers, organizer_headers, auth_headers, db_factory
):
    contest = create_contest(client, admin_headers, "Foreign removal", "SCHEDULED")
    registration = register_for_contest(client, auth_headers, contest["contest_id"])
    assert registration.status_code == 201

    # organizer_headers does not own this admin-created contest.
    removal = client.delete(
        f"/api/v1/contest-registrations/{registration.json()['registration_id']}",
        headers=organizer_headers,
    )
    assert removal.status_code == 403


def test_organizer_registration_listing_includes_user_identity(
    client, admin_headers, organizer_headers, auth_headers, registered_user
):
    """The organizer's participant view needs usernames and emails, not just ids."""
    payload = contest_payload("Identity listing contest")
    contest = client.post(
        "/api/v1/contests", json=payload, headers=organizer_headers
    ).json()
    client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "SCHEDULED"},
        headers=organizer_headers,
    )
    assert register_for_contest(client, auth_headers, contest["contest_id"]).status_code == 201

    listing = client.get(
        f"/api/v1/contest-registrations?contest_id={contest['contest_id']}",
        headers=organizer_headers,
    )
    assert listing.status_code == 200
    entries = listing.json()["registrations"]
    assert len(entries) == 1
    assert entries[0]["username"] == registered_user["username"]
    assert entries[0]["email"] == registered_user["email"]
