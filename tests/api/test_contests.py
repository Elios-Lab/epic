import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from epic_core.db.models import SensorObservation, SimulationSession, User
from epic_core.db.session import get_session_factory


def contest_payload(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "name": "EPIC Forecasting Challenge 2027",
        "description": "Test contest",
        "visibility": "PUBLIC",
        "twin_id": "mass_spring_damper",
        "sensor_configs": [{"sensor_id": "position"}],
        "fault_schedule": [],
        "initial_conditions": {"position": 0.1},
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


def create_user_headers(
    client, admin_headers, username: str, email: str, password: str
) -> dict:
    response = client.post(
        "/api/v1/users",
        json={"username": username, "email": email, "password": password},
        headers=admin_headers,
    )
    assert response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def create_organizer_headers(
    client, admin_headers, username: str, email: str, password: str
) -> dict:
    response = client.post(
        "/api/v1/users",
        json={"username": username, "email": email, "password": password},
        headers=admin_headers,
    )
    assert response.status_code == 201

    async def promote_organizer():
        async with get_session_factory()() as db:
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalar_one()
            user.role = "ORGANIZER"
            await db.commit()

    asyncio.run(promote_organizer())
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def register_for_contest(client, headers, contest_id: str) -> None:
    response = client.post(
        "/api/v1/contest-registrations",
        json={"contest_id": contest_id},
        headers=headers,
    )
    assert response.status_code == 201


def submit_for_contest(client, headers, contest_id: str):
    response = client.post(
        f"/api/v1/contests/{contest_id}/submissions",
        json={
            "task_id": "forecasting",
            "prediction_from_sequence": 1,
            "payload": {"forecast": {"horizon_1": {"position": 0.12}}},
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def add_observation_for_contest(db_factory, contest_id: str) -> None:
    async def insert_observation():
        async with db_factory() as db:
            result = await db.execute(
                select(SimulationSession).where(
                    SimulationSession.contest_id == UUID(contest_id)
                )
            )
            session = result.scalar_one()
            observation = SensorObservation(
                session_id=session.id,
                sequence_id=1,
                timestamp=datetime.now(timezone.utc) - timedelta(seconds=1),
                sensors={"position": 0.1},
                labels=None,
            )
            db.add(observation)
            await db.commit()

    asyncio.run(insert_observation())


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
    assert body["twin_id"] == "mass_spring_damper"
    assert body["sensor_configs"] == [{"sensor_id": "position"}]


def test_create_contest_as_participant_returns_403(client, auth_headers):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(),
        headers=auth_headers,
    )

    assert response.status_code == 403


def test_create_contest_as_organizer_returns_201(
    client, organizer_headers, registered_organizer
):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(name="Organizer contest"),
        headers=organizer_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["created_by"] == registered_organizer["id"]


def test_create_contest_with_unknown_twin_returns_404(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(twin_id="unknown_twin"),
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLUGIN_NOT_FOUND"


def test_create_contest_with_unknown_sensor_returns_404(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=contest_payload(sensor_configs=[{"sensor_id": "unknown_sensor"}]),
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLUGIN_NOT_FOUND"


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
    contest_ids = {item["contest_id"] for item in body["contests"]}
    assert contest["contest_id"] in contest_ids


def test_list_contests_with_status_filter_returns_matching_contests(
    client, admin_headers
):
    draft = create_contest(client, admin_headers, name="Draft contest")
    scheduled = create_contest(client, admin_headers, name="Scheduled contest")
    schedule_response = client.patch(
        f"/api/v1/contests/{scheduled['contest_id']}",
        json={"status": "SCHEDULED"},
        headers=admin_headers,
    )
    assert schedule_response.status_code == 200

    response = client.get("/api/v1/contests", params={"status": "DRAFT"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    contest_ids = {item["contest_id"] for item in body["contests"]}
    assert draft["contest_id"] in contest_ids
    assert scheduled["contest_id"] not in contest_ids


def test_get_contest_returns_contest(client, admin_headers):
    contest = create_contest(client, admin_headers)

    response = client.get(f"/api/v1/contests/{contest['contest_id']}")

    assert response.status_code == 200
    assert response.json()["contest_id"] == contest["contest_id"]


def test_get_nonexistent_contest_returns_404(client):
    response = client.get("/api/v1/contests/nonexistent")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONTEST_NOT_FOUND"


def test_patch_draft_to_active_creates_session(client, admin_headers, db_factory):
    contest = create_contest(client, admin_headers)

    response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"

    async def load_session():
        async with db_factory() as db:
            result = await db.execute(
                select(SimulationSession).where(
                    SimulationSession.contest_id == UUID(contest["contest_id"])
                )
            )
            return result.scalar_one_or_none()

    session = asyncio.run(load_session())
    assert session is not None


def test_patch_contest_by_creator_organizer_returns_200(client, organizer_headers):
    contest = create_contest(
        client,
        organizer_headers,
        name="Organizer managed contest",
    )

    response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "SCHEDULED"},
        headers=organizer_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SCHEDULED"


def test_patch_contest_by_different_organizer_returns_403(
    client, organizer_headers, admin_headers
):
    contest = create_contest(
        client,
        organizer_headers,
        name="Organizer owned contest",
    )
    other_organizer_headers = create_organizer_headers(
        client,
        admin_headers,
        "organizer2",
        "organizer2@example.com",
        "organizer2-password",
    )

    response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "SCHEDULED"},
        headers=other_organizer_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_patch_draft_to_closed_returns_409(client, admin_headers):
    contest = create_contest(client, admin_headers)

    response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
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
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )
    assert active_response.status_code == 200

    new_end_date = datetime.now(timezone.utc) + timedelta(seconds=5)
    response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
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
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )
    assert active_response.status_code == 200

    response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"end_date": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_contest_as_participant_returns_403(client, admin_headers, auth_headers):
    contest = create_contest(client, admin_headers)

    response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "ACTIVE"},
        headers=auth_headers,
    )

    assert response.status_code == 403


def test_patch_active_to_closed_sets_end_date(client, admin_headers):
    contest = create_contest(client, admin_headers)
    active_response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )
    assert active_response.status_code == 200

    response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "CLOSED"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CLOSED"
    assert body["end_date"] is not None


def test_organizer_sees_all_own_contest_submissions_participant_sees_own(
    client, organizer_headers, auth_headers, admin_headers, db_factory
):
    contest = create_contest(
        client,
        organizer_headers,
        name="Organizer submission visibility",
        end_date=(datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat(),
    )
    active_response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "ACTIVE"},
        headers=organizer_headers,
    )
    assert active_response.status_code == 200
    add_observation_for_contest(db_factory, contest["contest_id"])

    other_headers = create_user_headers(
        client,
        admin_headers,
        "student-for-organizer-view",
        "student-for-organizer-view@example.com",
        "participant-password",
    )
    register_for_contest(client, auth_headers, contest["contest_id"])
    register_for_contest(client, other_headers, contest["contest_id"])
    own_submission = submit_for_contest(client, auth_headers, contest["contest_id"])
    other_submission = submit_for_contest(client, other_headers, contest["contest_id"])

    organizer_response = client.get(
        f"/api/v1/contests/{contest['contest_id']}/submissions",
        headers=organizer_headers,
    )
    participant_response = client.get(
        f"/api/v1/contests/{contest['contest_id']}/submissions",
        headers=auth_headers,
    )

    assert organizer_response.status_code == 200
    organizer_ids = {
        submission["submission_id"]
        for submission in organizer_response.json()["submissions"]
    }
    assert own_submission["submission_id"] in organizer_ids
    assert other_submission["submission_id"] in organizer_ids

    assert participant_response.status_code == 200
    participant_ids = {
        submission["submission_id"]
        for submission in participant_response.json()["submissions"]
    }
    assert own_submission["submission_id"] in participant_ids
    assert other_submission["submission_id"] not in participant_ids
