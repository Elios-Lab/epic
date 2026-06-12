import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from epic.core.db.models import SensorObservation, SimulationSession, User
from epic.core.db.session import get_session_factory


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
        "start_date": (now - timedelta(seconds=10)).isoformat(),
        "end_of_observation": (now - timedelta(seconds=2)).isoformat(),
        "prediction_horizon_seconds": 0.1,
        "end_date": (now + timedelta(seconds=30)).isoformat(),
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
            "payload": {"forecast": {"position": [0.12, 0.13]}},
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def force_contest_status(db_factory, contest_id: str, status: str) -> None:
    """Set contest status directly in the DB without starting the engine."""
    from epic.core.db.models import Contest as ContestModel
    async def _set():
        async with db_factory() as db:
            result = await db.execute(
                select(ContestModel).where(ContestModel.id == UUID(contest_id))
            )
            contest = result.scalar_one()
            contest.status = status
            await db.commit()
    asyncio.run(_set())


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


def test_create_contest_with_duplicate_name_returns_422(client, admin_headers):
    create_contest(client, admin_headers, name="Duplicate Name Contest")

    response = client.post(
        "/api/v1/contests",
        json=contest_payload(name="Duplicate Name Contest"),
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "Duplicate Name Contest" in body["error"]["message"]


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

    response = client.get("/api/v1/contests", headers=admin_headers)

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

    response = client.get(
        "/api/v1/contests", params={"status": "DRAFT"}, headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    contest_ids = {item["contest_id"] for item in body["contests"]}
    assert draft["contest_id"] in contest_ids
    assert scheduled["contest_id"] not in contest_ids


def test_get_contest_returns_contest(client, admin_headers):
    contest = create_contest(client, admin_headers)

    response = client.get(
        f"/api/v1/contests/{contest['contest_id']}", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["contest_id"] == contest["contest_id"]


def test_get_nonexistent_contest_returns_404(client, admin_headers):
    response = client.get("/api/v1/contests/nonexistent", headers=admin_headers)

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


# ── Delete contest ────────────────────────────────────────────────────

def test_delete_draft_contest_returns_204(client, admin_headers):
    contest = create_contest(client, admin_headers, name="Delete draft contest")
    contest_id = contest["contest_id"]

    response = client.delete(
        f"/api/v1/contests/{contest_id}",
        headers=admin_headers,
    )

    assert response.status_code == 204
    get_response = client.get(
        f"/api/v1/contests/{contest_id}", headers=admin_headers
    )
    assert get_response.status_code == 404


def test_delete_contest_removes_all_associated_data(
    client, admin_headers, auth_headers, db_factory
):
    """Deleting a CLOSED contest must remove tasks, registrations, submissions,
    scores, leaderboard entries, simulation session, and sensor observations."""
    import asyncio, time
    from sqlalchemy import select
    from epic.core.db.models import (
        Task, ContestRegistration, Submission, Score,
        LeaderboardEntry, SimulationSession, SensorObservation,
    )
    from uuid import UUID
    from epic.api.routers.submissions import _score_submission

    # Create and activate contest
    contest = create_contest(
        client, admin_headers,
        name="Delete full data contest",
        sampling_rate_hz=20.0,
        end_date=(datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(),
    )
    contest_id = contest["contest_id"]

    client.patch(f"/api/v1/contests/{contest_id}",
        json={"status": "SCHEDULED"}, headers=admin_headers)

    register_for_contest(client, auth_headers, contest_id)

    client.patch(f"/api/v1/contests/{contest_id}",
        json={"status": "ACTIVE"}, headers=admin_headers)

    add_observation_for_contest(db_factory, contest_id)
    submission = submit_for_contest(client, auth_headers, contest_id)
    sub_id = UUID(submission["submission_id"])
    asyncio.run(_score_submission(sub_id, db_factory))

    # Close the contest before deleting
    client.patch(f"/api/v1/contests/{contest_id}",
        json={"status": "CLOSED"}, headers=admin_headers)

    # Delete
    response = client.delete(
        f"/api/v1/contests/{contest_id}", headers=admin_headers
    )
    assert response.status_code == 204

    # Verify every related table is empty for this contest
    async def assert_all_deleted():
        cid = UUID(contest_id)
        async with db_factory() as db:
            assert (await db.execute(
                select(Task).where(Task.contest_id == cid)
            )).scalar_one_or_none() is None, "Task not deleted"

            assert (await db.execute(
                select(ContestRegistration).where(ContestRegistration.contest_id == cid)
            )).scalar_one_or_none() is None, "ContestRegistration not deleted"

            assert (await db.execute(
                select(Submission).where(Submission.contest_id == cid)
            )).scalar_one_or_none() is None, "Submission not deleted"

            assert (await db.execute(
                select(LeaderboardEntry).where(LeaderboardEntry.contest_id == cid)
            )).scalar_one_or_none() is None, "LeaderboardEntry not deleted"

            assert (await db.execute(
                select(SimulationSession).where(SimulationSession.contest_id == cid)
            )).scalar_one_or_none() is None, "SimulationSession not deleted"

            # Scores and SensorObservations are grandchildren — verify via
            # the now-deleted submission/session ids
            assert (await db.execute(
                select(Score).where(Score.submission_id == sub_id)
            )).scalar_one_or_none() is None, "Score not deleted"

    asyncio.run(assert_all_deleted())


def test_delete_active_contest_returns_409(client, admin_headers):
    contest = create_contest(
        client, admin_headers,
        name="Delete active contest",
        end_date=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )
    contest_id = contest["contest_id"]
    client.patch(f"/api/v1/contests/{contest_id}",
        json={"status": "ACTIVE"}, headers=admin_headers)

    response = client.delete(
        f"/api/v1/contests/{contest_id}", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTEST_STATE_ERROR"


def test_delete_nonexistent_contest_returns_404(client, admin_headers):
    import uuid
    response = client.delete(
        f"/api/v1/contests/{uuid.uuid4()}",
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_delete_own_contest_by_organizer_returns_204(client, organizer_headers):
    """An organizer can delete a contest they created."""
    contest = create_contest(
        client, organizer_headers, name="Delete own organizer contest"
    )
    contest_id = contest["contest_id"]

    response = client.delete(
        f"/api/v1/contests/{contest_id}",
        headers=organizer_headers,
    )

    assert response.status_code == 204
    assert (
        client.get(f"/api/v1/contests/{contest_id}", headers=organizer_headers).status_code
        == 404
    )


def test_delete_other_organizers_contest_returns_403(
    client, admin_headers, organizer_headers
):
    """An organizer cannot delete a contest created by a different organizer."""
    other_org_headers = create_organizer_headers(
        client, admin_headers,
        "other-org-delete", "other-org-delete@example.com", "password"
    )
    contest = create_contest(client, other_org_headers, name="Other organizer contest to protect")

    response = client.delete(
        f"/api/v1/contests/{contest['contest_id']}",
        headers=organizer_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_delete_contest_by_participant_returns_403(
    client, admin_headers, auth_headers
):
    contest = create_contest(
        client, admin_headers, name="Delete by participant contest"
    )
    response = client.delete(
        f"/api/v1/contests/{contest['contest_id']}",
        headers=auth_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_delete_archived_contest_returns_204(client, admin_headers):
    contest = create_contest(
        client, admin_headers,
        name="Delete archived contest",
        end_date=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )
    contest_id = contest["contest_id"]
    for status in ("ACTIVE", "CLOSED", "ARCHIVED"):
        r = client.patch(f"/api/v1/contests/{contest_id}",
            json={"status": status}, headers=admin_headers)
        assert r.status_code == 200, f"Failed to transition to {status}: {r.text}"

    response = client.delete(
        f"/api/v1/contests/{contest_id}", headers=admin_headers
    )
    assert response.status_code == 204


# ── Pause / Resume ────────────────────────────────────────────────────

def test_pause_active_contest_returns_200(client, admin_headers, db_factory):
    contest = create_contest(client, admin_headers, name="Pause active contest")
    contest_id = contest["contest_id"]
    force_contest_status(db_factory, contest_id, "ACTIVE")

    response = client.put(
        f"/api/v1/contests/{contest_id}/pause", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "PAUSED"


def test_pause_non_active_contest_returns_409(client, admin_headers):
    contest = create_contest(client, admin_headers, name="Pause draft contest")

    response = client.put(
        f"/api/v1/contests/{contest['contest_id']}/pause", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTEST_STATE_ERROR"


def test_pause_by_owner_organizer_returns_200(client, organizer_headers, db_factory):
    contest = create_contest(
        client, organizer_headers,
        name="Pause by owner organizer",
    )
    contest_id = contest["contest_id"]
    force_contest_status(db_factory, contest_id, "ACTIVE")

    response = client.put(
        f"/api/v1/contests/{contest_id}/pause", headers=organizer_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "PAUSED"


def test_pause_by_different_organizer_returns_403(
    client, admin_headers, organizer_headers, db_factory
):
    other_org = create_organizer_headers(
        client, admin_headers,
        "other-org-pause", "other-org-pause@example.com", "password"
    )
    contest = create_contest(
        client, other_org,
        name="Pause by different organizer",
    )
    contest_id = contest["contest_id"]
    force_contest_status(db_factory, contest_id, "ACTIVE")

    response = client.put(
        f"/api/v1/contests/{contest_id}/pause", headers=organizer_headers
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_pause_by_participant_returns_403(client, admin_headers, auth_headers, db_factory):
    contest = create_contest(client, admin_headers, name="Pause by participant")
    contest_id = contest["contest_id"]
    force_contest_status(db_factory, contest_id, "ACTIVE")

    response = client.put(
        f"/api/v1/contests/{contest_id}/pause", headers=auth_headers
    )

    assert response.status_code == 403


def test_resume_paused_contest_returns_200(client, admin_headers, db_factory):
    contest = create_contest(
        client, admin_headers,
        name="Resume paused contest",
        end_date=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )
    contest_id = contest["contest_id"]
    # ACTIVE creates the SimulationSession needed by the resume endpoint.
    client.patch(f"/api/v1/contests/{contest_id}",
        json={"status": "ACTIVE"}, headers=admin_headers)
    # Force-set PAUSED directly to avoid the engine race condition.
    force_contest_status(db_factory, contest_id, "PAUSED")

    response = client.put(
        f"/api/v1/contests/{contest_id}/resume", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"


def test_resume_non_paused_contest_returns_409(client, admin_headers):
    contest = create_contest(client, admin_headers, name="Resume draft contest")

    response = client.put(
        f"/api/v1/contests/{contest['contest_id']}/resume", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTEST_STATE_ERROR"


def test_resume_expired_contest_returns_409(client, admin_headers):
    """A paused contest whose end_date has passed cannot be resumed without extending."""
    import time
    contest = create_contest(
        client, admin_headers,
        name="Resume expired contest",
        end_date=(datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(),
    )
    contest_id = contest["contest_id"]
    client.patch(f"/api/v1/contests/{contest_id}",
        json={"status": "ACTIVE"}, headers=admin_headers)
    client.put(f"/api/v1/contests/{contest_id}/pause", headers=admin_headers)
    time.sleep(3)  # let the end_date expire

    response = client.put(
        f"/api/v1/contests/{contest_id}/resume", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTEST_STATE_ERROR"


def test_paused_contest_can_be_closed(client, admin_headers, db_factory):
    """PAUSED → CLOSED via PATCH is allowed without resuming first."""
    contest = create_contest(
        client, admin_headers,
        name="Close paused contest",
        end_date=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )
    contest_id = contest["contest_id"]
    force_contest_status(db_factory, contest_id, "PAUSED")

    response = client.patch(
        f"/api/v1/contests/{contest_id}",
        json={"status": "CLOSED"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"


def test_paused_contest_deadline_can_be_extended(client, admin_headers, db_factory):
    """Extending the deadline on a PAUSED contest must succeed."""
    contest = create_contest(
        client, admin_headers,
        name="Extend deadline paused contest",
        end_date=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )
    contest_id = contest["contest_id"]
    force_contest_status(db_factory, contest_id, "PAUSED")

    new_end = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    response = client.patch(
        f"/api/v1/contests/{contest_id}",
        json={"end_date": new_end},
        headers=admin_headers,
    )

    assert response.status_code == 200


# ── Two-phase contests ────────────────────────────────────────────────

def two_phase_payload(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "name": "Two-Phase Challenge",
        "visibility": "PUBLIC",
        "twin_id": "mass_spring_damper",
        "sensor_configs": [{"sensor_id": "position"}],
        "fault_schedule": [],
        "sampling_rate_hz": 10.0,
        "start_date": now.isoformat(),
        "end_of_observation": (now + timedelta(seconds=5)).isoformat(),
        "prediction_horizon_seconds": 2.0,
        "end_date": (now + timedelta(seconds=20)).isoformat(),
        "metric_ids": ["mae"],
    }
    payload.update(overrides)
    return payload


def test_create_two_phase_contest_returns_correct_fields(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=two_phase_payload(),
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["end_of_observation"] is not None
    assert body["prediction_horizon_seconds"] == 2.0
    tasks = body["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["configuration"]["eval_steps"] == 20  # 2.0s * 10Hz
    assert tasks[0]["configuration"]["prediction_horizon_seconds"] == 2.0
    assert tasks[0]["configuration"]["score_against"] == "ground_truth"
    assert tasks[0]["configuration"]["target_variables"] == ["position"]


def test_create_contest_with_explicit_target_variables(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=two_phase_payload(
            sensor_configs=[
                {"sensor_id": "position"},
                {"sensor_id": "velocity"},
            ],
            target_variables=["velocity"],
        ),
        headers=admin_headers,
    )
    assert response.status_code == 201
    cfg = response.json()["tasks"][0]["configuration"]
    assert cfg["target_variables"] == ["velocity"]


def test_create_contest_with_empty_target_variables_returns_422(
    client, admin_headers
):
    response = client.post(
        "/api/v1/contests",
        json=two_phase_payload(target_variables=[]),
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_contest_with_unconfigured_target_variable_returns_422(
    client, admin_headers
):
    response = client.post(
        "/api/v1/contests",
        json=two_phase_payload(target_variables=["velocity"]),
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_contest_with_explicit_score_against_sensors(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=two_phase_payload(score_against="sensors"),
        headers=admin_headers,
    )
    assert response.status_code == 201
    cfg = response.json()["tasks"][0]["configuration"]
    assert cfg["score_against"] == "sensors"


def test_create_contest_with_invalid_score_against_returns_422(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=two_phase_payload(score_against="raw"),
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_two_phase_contest_missing_horizon_returns_422(client, admin_headers):
    payload = two_phase_payload()
    del payload["prediction_horizon_seconds"]
    response = client.post("/api/v1/contests", json=payload, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_two_phase_contest_end_date_too_early_returns_422(client, admin_headers):
    now = datetime.now(timezone.utc)
    response = client.post(
        "/api/v1/contests",
        json=two_phase_payload(
            end_of_observation=(now + timedelta(seconds=5)).isoformat(),
            prediction_horizon_seconds=2.0,
            # end_date before end_of_evaluation (5+2=7 s) → invalid
            end_date=(now + timedelta(seconds=6)).isoformat(),
        ),
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_two_phase_contest_with_unknown_metric_returns_422(client, admin_headers):
    response = client.post(
        "/api/v1/contests",
        json=two_phase_payload(metric_ids=["nonexistent_metric"]),
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_two_phase_submission_rejected_before_eval_ends(client, admin_headers, auth_headers):
    """Submissions must be rejected while the evaluation window is still running."""
    now = datetime.now(timezone.utc)
    response = client.post(
        "/api/v1/contests",
        json=two_phase_payload(
            name="Early submission two-phase",
            prediction_horizon_seconds=3600.0,  # 1 hour — evaluation not yet done
            end_date=(now + timedelta(hours=2)).isoformat(),
        ),
        headers=admin_headers,
    )
    assert response.status_code == 201
    contest_id = response.json()["contest_id"]
    client.patch(f"/api/v1/contests/{contest_id}",
        json={"status": "ACTIVE"}, headers=admin_headers)
    register_for_contest(client, auth_headers, contest_id)

    sub_response = client.post(
        f"/api/v1/contests/{contest_id}/submissions",
        json={"task_id": "forecasting", "payload": {"forecast": {"position": [0.1]}}},
        headers=auth_headers,
    )

    assert sub_response.status_code == 409
    assert sub_response.json()["error"]["code"] == "CONTEST_STATE_ERROR"


# ── Listing and get visibility ───────────────────────────────────────────────

def test_list_contests_requires_authentication(client):
    response = client.get("/api/v1/contests")
    assert response.status_code == 401


def _restricted_contest(client, organizer_headers, name, visibility, status="SCHEDULED"):
    payload = contest_payload()
    payload["name"] = name
    payload["visibility"] = visibility
    response = client.post("/api/v1/contests", json=payload, headers=organizer_headers)
    assert response.status_code == 201, response.json()
    contest = response.json()
    if status != "DRAFT":
        patched = client.patch(
            f"/api/v1/contests/{contest['contest_id']}",
            json={"status": status},
            headers=organizer_headers,
        )
        assert patched.status_code == 200
        contest = patched.json()
    return contest


def test_participant_does_not_see_drafts_or_restricted_contests(
    client, admin_headers, organizer_headers, auth_headers
):
    draft = _restricted_contest(
        client, organizer_headers, "Hidden draft", "PUBLIC", status="DRAFT"
    )
    private = _restricted_contest(client, organizer_headers, "Hidden private", "PRIVATE")
    public = _restricted_contest(client, organizer_headers, "Visible public", "PUBLIC")

    response = client.get("/api/v1/contests", headers=auth_headers)
    assert response.status_code == 200
    visible_ids = {c["contest_id"] for c in response.json()["contests"]}

    assert public["contest_id"] in visible_ids
    assert draft["contest_id"] not in visible_ids
    assert private["contest_id"] not in visible_ids

    # Direct GET of a hidden contest is a 404, not a 403 — no existence leak.
    for hidden in (draft, private):
        get_response = client.get(
            f"/api/v1/contests/{hidden['contest_id']}", headers=auth_headers
        )
        assert get_response.status_code == 404


def test_invited_participant_sees_restricted_contest(
    client, organizer_headers, auth_headers, registered_user
):
    contest = _restricted_contest(
        client, organizer_headers, "Private-but-invited", "PRIVATE"
    )
    invite = client.post(
        f"/api/v1/contests/{contest['contest_id']}/invitations",
        json={"emails": [registered_user["email"]]},
        headers=organizer_headers,
    )
    assert invite.status_code == 201

    listing = client.get("/api/v1/contests", headers=auth_headers)
    visible_ids = {c["contest_id"] for c in listing.json()["contests"]}
    assert contest["contest_id"] in visible_ids

    get_response = client.get(
        f"/api/v1/contests/{contest['contest_id']}", headers=auth_headers
    )
    assert get_response.status_code == 200


def test_organizer_sees_own_draft_but_not_others_private(
    client, admin_headers, organizer_headers
):
    own_draft = _restricted_contest(
        client, organizer_headers, "Own draft", "PUBLIC", status="DRAFT"
    )
    # A different owner: the admin creates a private contest.
    payload = contest_payload()
    payload["name"] = "Admin private"
    payload["visibility"] = "PRIVATE"
    admin_private = client.post(
        "/api/v1/contests", json=payload, headers=admin_headers
    ).json()
    client.patch(
        f"/api/v1/contests/{admin_private['contest_id']}",
        json={"status": "SCHEDULED"},
        headers=admin_headers,
    )

    listing = client.get("/api/v1/contests", headers=organizer_headers)
    visible_ids = {c["contest_id"] for c in listing.json()["contests"]}
    assert own_draft["contest_id"] in visible_ids
    assert admin_private["contest_id"] not in visible_ids


def test_admin_sees_everything(client, admin_headers, organizer_headers):
    draft = _restricted_contest(
        client, organizer_headers, "Admin-view draft", "PUBLIC", status="DRAFT"
    )
    private = _restricted_contest(
        client, organizer_headers, "Admin-view private", "PRIVATE"
    )

    listing = client.get("/api/v1/contests", headers=admin_headers)
    visible_ids = {c["contest_id"] for c in listing.json()["contests"]}
    assert draft["contest_id"] in visible_ids
    assert private["contest_id"] in visible_ids
