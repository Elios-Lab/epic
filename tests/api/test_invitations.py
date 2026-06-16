"""Tests for the competition-scoped participant invitation workflow."""

import asyncio
from sqlalchemy import select
from epic_core.kernel.db.models import Invitation
from epic_core.kernel.db.session import get_session_factory


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_token_for_email(email: str) -> str:
    """Read the invitation token directly from the DB (tokens are not returned by the API)."""
    async def _query():
        async with get_session_factory()() as db:
            result = await db.execute(select(Invitation).where(Invitation.email == email))
            inv = result.scalar_one()
            return inv.token

    return asyncio.run(_query())


# ── Invitation creation ───────────────────────────────────────────────────────

def test_organizer_creates_invitations_returns_201(
    client, organizer_headers, registered_contest
):
    response = client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com", "charlie@example.com"]},
        headers=organizer_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created"] == 2
    assert len(body["invitations"]) == 2
    emails = {inv["email"] for inv in body["invitations"]}
    assert emails == {"bob@example.com", "charlie@example.com"}


def test_create_invitations_sends_email_per_address(
    client, organizer_headers, registered_contest, collecting_notifications
):
    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=organizer_headers,
    )

    assert len(collecting_notifications.participant_invitations) == 1
    assert collecting_notifications.participant_invitations[0]["to_email"] == "bob@example.com"


def test_create_invitations_response_does_not_expose_token(
    client, organizer_headers, registered_contest
):
    """Tokens must only be delivered via email, not returned in the API response."""
    response = client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=organizer_headers,
    )

    body = response.json()
    for inv in body["invitations"]:
        assert "token" not in inv


def test_create_invitations_as_participant_returns_403(
    client, auth_headers, registered_contest
):
    response = client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=auth_headers,
    )
    assert response.status_code == 403


def test_create_invitations_for_unknown_contest_returns_404(
    client, organizer_headers
):
    import uuid
    response = client.post(
        f"/api/v1/contests/{uuid.uuid4()}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=organizer_headers,
    )
    assert response.status_code == 404


# ── Token validation ──────────────────────────────────────────────────────────

def test_get_valid_invitation_returns_200(
    client, organizer_headers, registered_contest
):
    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=organizer_headers,
    )
    token = _get_token_for_email("bob@example.com")

    response = client.get(f"/api/v1/invitations/{token}")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "bob@example.com"
    assert body["contest_id"] == registered_contest["contest_id"]
    assert body["valid"] is True


def test_get_unknown_token_returns_404(client):
    response = client.get("/api/v1/invitations/nonexistent-token-xyz")
    assert response.status_code == 404


# ── Invitation acceptance ─────────────────────────────────────────────────────

def test_accept_invitation_creates_participant_account(
    client, organizer_headers, registered_contest
):
    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=organizer_headers,
    )
    token = _get_token_for_email("bob@example.com")

    response = client.post(
        f"/api/v1/invitations/{token}/accept",
        json={
            "first_name": "Bob",
            "last_name": "Jones",
            "phone_number": "+39012345678",
            "password": "bob-secret-123",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "bob@example.com"
    assert body["user"]["role"] == "PARTICIPANT"
    assert body["user"]["status"] == "ACTIVE"
    assert body["access_token"]


def test_accept_invitation_participant_can_login(
    client, organizer_headers, registered_contest
):
    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=organizer_headers,
    )
    token = _get_token_for_email("bob@example.com")
    client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"first_name": "Bob", "last_name": "Jones", "password": "bob-secret-123"},
    )

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "bob@example.com", "password": "bob-secret-123"},
    )
    assert login.status_code == 200


def test_accept_invitation_marks_token_as_used(
    client, organizer_headers, registered_contest
):
    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=organizer_headers,
    )
    token = _get_token_for_email("bob@example.com")
    client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"first_name": "Bob", "last_name": "Jones", "password": "bob-secret-123"},
    )

    # Second acceptance with the same token must fail
    response = client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"first_name": "Eve", "last_name": "Evil", "password": "hacked"},
    )
    assert response.status_code == 410


def test_accept_invitation_unknown_token_returns_404(client):
    response = client.post(
        "/api/v1/invitations/nonexistent-token/accept",
        json={"first_name": "Bob", "last_name": "Jones", "password": "pass"},
    )
    assert response.status_code == 404


def test_accept_expired_invitation_returns_410(
    client, organizer_headers, registered_contest
):
    """An invitation whose expires_at is in the past must be rejected."""
    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=organizer_headers,
    )
    token = _get_token_for_email("bob@example.com")

    # Force expiry directly in the DB
    async def _expire():
        from datetime import timedelta, timezone
        from datetime import datetime
        async with get_session_factory()() as db:
            result = await db.execute(select(Invitation).where(Invitation.token == token))
            inv = result.scalar_one()
            inv.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await db.commit()

    asyncio.run(_expire())

    response = client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"first_name": "Bob", "last_name": "Jones", "password": "bob-secret-123"},
    )
    assert response.status_code == 410


def test_accept_invitation_user_linked_to_contest(
    client, organizer_headers, registered_contest, admin_headers
):
    """The created participant account must be linked back to the invitation's contest."""
    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["bob@example.com"]},
        headers=organizer_headers,
    )
    token = _get_token_for_email("bob@example.com")
    accepted = client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"first_name": "Bob", "last_name": "Jones", "password": "bob-secret-123"},
    ).json()

    async def _check():
        async with get_session_factory()() as db:
            result = await db.execute(select(Invitation).where(Invitation.token == token))
            inv = result.scalar_one()
            return str(inv.user_id), str(inv.contest_id)

    user_id, contest_id = asyncio.run(_check())
    assert user_id == accepted["user"]["id"]
    assert contest_id == registered_contest["contest_id"]


def test_accept_invitation_creates_contest_registration(
    client, organizer_headers, registered_contest
):
    """Accepting an invitation must register the participant for the contest,
    so they can stream and submit with no further steps (as documented)."""
    from epic_core.kernel.db.models import ContestRegistration

    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["carla@example.com"]},
        headers=organizer_headers,
    )
    token = _get_token_for_email("carla@example.com")
    accepted = client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"first_name": "Carla", "last_name": "Rossi", "password": "carla-secret-123"},
    ).json()

    async def _check():
        from uuid import UUID

        async with get_session_factory()() as db:
            result = await db.execute(
                select(ContestRegistration).where(
                    ContestRegistration.user_id == UUID(accepted["user"]["id"]),
                )
            )
            return result.scalar_one_or_none()

    registration = asyncio.run(_check())
    assert registration is not None
    assert str(registration.contest_id) == registered_contest["contest_id"]
    assert registration.status == "REGISTERED"


def test_register_deep_link_serves_spa(client):
    """/register?token=… (from invitation emails) must serve the SPA, not 404."""
    response = client.get("/register?token=whatever")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="auth-app"' in response.text


def test_quickstart_notebook_is_served(client):
    response = client.get("/notebooks/quickstart.ipynb")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ipynb+json")
    assert b"EPIC" in response.content


# ── Organizer invitation management ───────────────────────────────────────────

def test_owner_lists_contest_invitations(client, organizer_headers, registered_contest):
    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["x1@example.com", "x2@example.com"]},
        headers=organizer_headers,
    )

    response = client.get(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        headers=organizer_headers,
    )

    assert response.status_code == 200
    invitations = response.json()["invitations"]
    assert {inv["email"] for inv in invitations} == {"x1@example.com", "x2@example.com"}
    assert all(inv["used"] is False for inv in invitations)
    assert all("token" not in inv for inv in invitations)


def test_non_owner_organizer_cannot_list_or_create_invitations(
    client, admin_headers, organizer_headers
):
    """Invitation management is scoped to the contest owner."""
    from tests.api.test_registrations import contest_payload

    payload = contest_payload("Admin-owned for invitations")
    contest = client.post("/api/v1/contests", json=payload, headers=admin_headers).json()

    listing = client.get(
        f"/api/v1/contests/{contest['contest_id']}/invitations",
        headers=organizer_headers,
    )
    assert listing.status_code == 403

    creating = client.post(
        f"/api/v1/contests/{contest['contest_id']}/invitations",
        json={"emails": ["y@example.com"]},
        headers=organizer_headers,
    )
    assert creating.status_code == 403


def test_owner_revokes_unused_invitation(client, organizer_headers, registered_contest):
    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["revoke-me@example.com"]},
        headers=organizer_headers,
    )
    listing = client.get(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        headers=organizer_headers,
    ).json()
    invitation_id = listing["invitations"][0]["id"]
    token = _get_token_for_email("revoke-me@example.com")

    response = client.delete(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations/{invitation_id}",
        headers=organizer_headers,
    )
    assert response.status_code == 204

    # The invitation is gone and its registration link is dead.
    after = client.get(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        headers=organizer_headers,
    ).json()
    assert after["invitations"] == []
    assert client.get(f"/api/v1/invitations/{token}").status_code == 404
