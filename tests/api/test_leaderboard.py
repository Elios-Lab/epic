import asyncio
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from epic_api.routers.submissions import _score_submission
from epic_core.db.models import Contest, SensorObservation, SimulationSession, Task


def create_user_and_headers(client, admin_headers, username: str, email: str, password: str):
    response = client.post(
        "/api/v1/users",
        json={"username": username, "email": email, "password": password},
        headers=admin_headers,
    )
    assert response.status_code == 201
    user = response.json()
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    return user, {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def create_active_contest_with_observations(db_factory, name: str = "Leaderboard"):
    async def create_records():
        now = datetime.now(timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name=name,
                description="Leaderboard test contest",
                status="ACTIVE",
                visibility="PUBLIC",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=20.0,
                start_date=now,
                end_date=now + timedelta(seconds=10),
                created_by=None,
            )
            db.add(contest)
            await db.flush()
            db.add(
                Task(
                    contest_id=contest.id,
                    task_type="FORECASTING",
                    name="FORECASTING",
                    metric_ids=[],
                    weight=1.0,
                    configuration={"forecast_horizons": [1]},
                )
            )
            await db.commit()
            await db.refresh(contest)

            session = SimulationSession(
                contest_id=contest.id,
                twin_id=contest.twin_id,
                sampling_rate_hz=contest.sampling_rate_hz,
                status="RUNNING",
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)

            for sequence_id, position in ((1, 0.1), (2, 0.2)):
                db.add(
                    SensorObservation(
                        session_id=session.id,
                        sequence_id=sequence_id,
                        timestamp=datetime.now(timezone.utc) - timedelta(seconds=1),
                        sensors={"position": position},
                        labels=None,
                    )
                )
            await db.commit()
            return contest

    return asyncio.run(create_records())


def register(client, headers, contest_id: str) -> None:
    response = client.post(
        "/api/v1/contest-registrations",
        json={"contest_id": contest_id},
        headers=headers,
    )
    assert response.status_code == 201


def submit_and_score(client, headers, db_factory, contest_id: str, prediction: float):
    response = client.post(
        f"/api/v1/contests/{contest_id}/submissions",
        json={
            "task_id": "forecasting",
            "prediction_from_sequence": 1,
            "payload": {"forecast": {"horizon_1": {"position": prediction}}},
        },
        headers=headers,
    )
    assert response.status_code == 201
    submission = response.json()
    for _ in range(20):
        status_response = client.get(
            f"/api/v1/submissions/{submission['submission_id']}", headers=headers
        )
        assert status_response.status_code == 200
        if status_response.json()["status"] == "EVALUATED":
            break
        time.sleep(0.05)
    asyncio.run(_score_submission(UUID(submission["submission_id"]), db_factory))
    return submission


def leaderboard_setup(client, db_factory, admin_headers):
    contest = create_active_contest_with_observations(db_factory)
    user1, headers1 = create_user_and_headers(
        client, admin_headers, "leaderboard1", "leaderboard1@example.com", "password1"
    )
    user2, headers2 = create_user_and_headers(
        client, admin_headers, "leaderboard2", "leaderboard2@example.com", "password2"
    )
    register(client, headers1, str(contest.id))
    register(client, headers2, str(contest.id))
    submission1 = submit_and_score(client, headers1, db_factory, str(contest.id), 0.4)
    submission2 = submit_and_score(client, headers2, db_factory, str(contest.id), 0.25)
    return {
        "contest": contest,
        "user1": user1,
        "headers1": headers1,
        "submission1": submission1,
        "user2": user2,
        "headers2": headers2,
        "submission2": submission2,
    }


def test_get_leaderboard_returns_entries_ordered_by_rank(client, db_factory, admin_headers):
    setup = leaderboard_setup(client, db_factory, admin_headers)

    response = client.get(f"/api/v1/contests/{setup['contest'].id}/leaderboard")

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert [entry["rank"] for entry in entries] == [1, 2]


def test_participant_with_lower_mae_has_rank_one(client, db_factory, admin_headers):
    setup = leaderboard_setup(client, db_factory, admin_headers)

    response = client.get(f"/api/v1/contests/{setup['contest'].id}/leaderboard")

    assert response.status_code == 200
    rank_one = response.json()["entries"][0]
    assert rank_one["user_id"] == setup["user2"]["id"]


def test_better_second_submission_replaces_leaderboard_entry(
    client, db_factory, admin_headers
):
    setup = leaderboard_setup(client, db_factory, admin_headers)

    better_submission = submit_and_score(
        client, setup["headers1"], db_factory, str(setup["contest"].id), 0.21
    )
    response = client.get(f"/api/v1/contests/{setup['contest'].id}/leaderboard")

    assert response.status_code == 200
    rank_one = response.json()["entries"][0]
    assert rank_one["user_id"] == setup["user1"]["id"]
    assert rank_one["submission_id"] == better_submission["submission_id"]


def test_get_user_leaderboard_entry_returns_entry(client, db_factory, admin_headers):
    setup = leaderboard_setup(client, db_factory, admin_headers)

    response = client.get(
        f"/api/v1/contests/{setup['contest'].id}/leaderboard/{setup['user2']['id']}",
        headers=setup["headers2"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == setup["user2"]["id"]
    assert body["rank"] == 1


def test_get_user_leaderboard_entry_by_different_participant_returns_403(
    client, db_factory, admin_headers
):
    setup = leaderboard_setup(client, db_factory, admin_headers)

    response = client.get(
        f"/api/v1/contests/{setup['contest'].id}/leaderboard/{setup['user2']['id']}",
        headers=setup["headers1"],
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
