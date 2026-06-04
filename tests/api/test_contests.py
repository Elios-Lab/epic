import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from epic_core.db.models import SimulationSession


def contest_payload(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "name": "EPIC Forecasting Challenge 2027",
        "description": "Test contest",
        "visibility": "PUBLIC",
        "twin_id": "mechanical_system",
        "scenario_id": "normal_operation",
        "sampling_rate_hz": 20.0,
        "start_date": now.isoformat(),
        "end_date": (now + timedelta(seconds=1)).isoformat(),
    }
    payload.update(overrides)
    return payload


def create_contest(client, admin_headers, **overrides):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(**overrides),
        headers=admin_headers,
    )
    assert response.status_code == 201
    return response.json()


def test_create_contest_as_admin_returns_draft(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(),
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["description"] == "Test contest"
    assert body["visibility"] == "PUBLIC"
    assert body["twin_id"] == "mechanical_system"
    assert body["scenario_id"] == "normal_operation"


def test_create_contest_as_participant_returns_403(client, auth_headers):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(),
        headers=auth_headers,
    )

    assert response.status_code == 403


def test_create_contest_with_unknown_twin_returns_404(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(twin_id="unknown_twin"),
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLUGIN_NOT_FOUND"


def test_create_contest_with_unknown_scenario_returns_422(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(scenario_id="unknown_scenario"),
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_contest_with_invalid_visibility_returns_422(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(visibility="HIDDEN"),
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_contests_returns_created_contest(client, admin_headers):
    contest = create_contest(client, admin_headers)

    response = client.get("/api/v1/contests")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    contest_ids = {item["id"] for item in body["contests"]}
    assert contest["id"] in contest_ids


def test_list_contests_with_status_filter_returns_matching_contests(
    client, admin_headers
):
    draft = create_contest(client, admin_headers, name="Draft contest")
    scheduled = create_contest(client, admin_headers, name="Scheduled contest")
    schedule_response = client.patch(
        f"/api/v1/contests/{scheduled['id']}",
        json={"status": "SCHEDULED"},
        headers=admin_headers,
    )
    assert schedule_response.status_code == 200

    response = client.get("/api/v1/contests", params={"status": "DRAFT"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    contest_ids = {item["id"] for item in body["contests"]}
    assert draft["id"] in contest_ids
    assert scheduled["id"] not in contest_ids


def test_get_contest_returns_contest(client, admin_headers):
    contest = create_contest(client, admin_headers)

    response = client.get(f"/api/v1/contests/{contest['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == contest["id"]


def test_get_nonexistent_contest_returns_404(client):
    response = client.get("/api/v1/contests/nonexistent")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONTEST_NOT_FOUND"


def test_patch_draft_to_active_creates_session(client, admin_headers, db_factory):
    contest = create_contest(client, admin_headers)

    response = client.patch(
        f"/api/v1/contests/{contest['id']}",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"

    async def load_session():
        async with db_factory() as db:
            result = await db.execute(
                select(SimulationSession).where(
                    SimulationSession.contest_id == UUID(contest["id"])
                )
            )
            return result.scalar_one_or_none()

    session = asyncio.run(load_session())
    assert session is not None


def test_patch_draft_to_closed_returns_409(client, admin_headers):
    contest = create_contest(client, admin_headers)

    response = client.patch(
        f"/api/v1/contests/{contest['id']}",
        json={"status": "CLOSED"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTEST_STATE_ERROR"


def test_patch_end_date_on_active_contest_updates_deadline(client, admin_headers):
    now = datetime.now(timezone.utc)
    contest = create_contest(
        client,
        admin_headers,
        start_date=now.isoformat(),
        end_date=(now + timedelta(seconds=3)).isoformat(),
    )
    active_response = client.patch(
        f"/api/v1/contests/{contest['id']}",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )
    assert active_response.status_code == 200

    new_end_date = datetime.now(timezone.utc) + timedelta(seconds=5)
    response = client.patch(
        f"/api/v1/contests/{contest['id']}",
        json={"end_date": new_end_date.isoformat()},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert datetime.fromisoformat(body["end_date"]).replace(
        tzinfo=timezone.utc
    ) == new_end_date


def test_patch_end_date_with_past_date_returns_422(client, admin_headers):
    now = datetime.now(timezone.utc)
    contest = create_contest(
        client,
        admin_headers,
        start_date=now.isoformat(),
        end_date=(now + timedelta(seconds=3)).isoformat(),
    )
    active_response = client.patch(
        f"/api/v1/contests/{contest['id']}",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )
    assert active_response.status_code == 200

    response = client.patch(
        f"/api/v1/contests/{contest['id']}",
        json={"end_date": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_contest_as_participant_returns_403(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers)

    response = client.patch(
        f"/api/v1/contests/{contest['id']}",
        json={"status": "ACTIVE"},
        headers=auth_headers,
    )

    assert response.status_code == 403


def test_patch_active_to_closed_sets_end_date(client, admin_headers):
    contest = create_contest(client, admin_headers)
    active_response = client.patch(
        f"/api/v1/contests/{contest['id']}",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )
    assert active_response.status_code == 200

    response = client.patch(
        f"/api/v1/contests/{contest['id']}",
        json={"status": "CLOSED"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CLOSED"
    assert body["end_date"] is not None
