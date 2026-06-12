import asyncio
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from epic.api.routers.submissions import _score_submission
from epic.core.db.models import Contest, Invitation, SensorObservation, SimulationSession, Task, User


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


_EVAL_STEPS = 1         # round(0.05 s * 20 Hz) = 1
_PREDICTION_HORIZON = 0.05
_SAMPLING_RATE = 20.0


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
                sampling_rate_hz=_SAMPLING_RATE,
                start_date=now - timedelta(seconds=10),
                end_date=now + timedelta(seconds=30),
                end_of_observation=now - timedelta(seconds=2),
                prediction_horizon_seconds=_PREDICTION_HORIZON,
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
                    configuration={"eval_steps": _EVAL_STEPS, "prediction_horizon_seconds": _PREDICTION_HORIZON},
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
            "payload": {"forecast": {"position": [prediction]}},
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

    response = client.get(
        f"/api/v1/contests/{setup['contest'].id}/leaderboard",
        headers=admin_headers,
    )

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert [entry["rank"] for entry in entries] == [1, 2]


def test_participant_with_lower_mae_has_rank_one(client, db_factory, admin_headers):
    setup = leaderboard_setup(client, db_factory, admin_headers)

    response = client.get(
        f"/api/v1/contests/{setup['contest'].id}/leaderboard",
        headers=admin_headers,
    )

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
    response = client.get(
        f"/api/v1/contests/{setup['contest'].id}/leaderboard",
        headers=admin_headers,
    )

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


def test_get_leaderboard_unauthenticated_returns_401(client, db_factory, admin_headers):
    contest = create_active_contest_with_observations(db_factory, name="AuthCheck")

    response = client.get(f"/api/v1/contests/{contest.id}/leaderboard")

    assert response.status_code == 401


def test_get_leaderboard_private_contest_denied_to_non_registered_user(
    client, db_factory, admin_headers
):
    async def create_private_contest():
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name="PrivateLeaderboard",
                status="ACTIVE",
                visibility="PRIVATE",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=10.0,
                start_date=now,
                end_date=now + __import__("datetime").timedelta(seconds=60),
                created_by=None,
            )
            db.add(contest)
            await db.commit()
            await db.refresh(contest)
            return contest

    import asyncio
    contest = asyncio.run(create_private_contest())

    _, outsider_headers = create_user_and_headers(
        client, admin_headers, "outsider_lb", "outsider_lb@example.com", "pass"
    )

    response = client.get(
        f"/api/v1/contests/{contest.id}/leaderboard",
        headers=outsider_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_get_leaderboard_private_contest_accessible_to_registered_participant(
    client, db_factory, admin_headers
):
    async def create_private_contest_with_obs():
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name="PrivateLeaderboardRegistered",
                status="ACTIVE",
                visibility="PRIVATE",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=10.0,
                start_date=now,
                end_date=now + dt.timedelta(seconds=60),
                created_by=None,
            )
            db.add(contest)
            await db.flush()
            db.add(Task(
                contest_id=contest.id,
                task_type="FORECASTING",
                name="FORECASTING",
                metric_ids=[],
                weight=1.0,
                configuration={"eval_steps": 1, "prediction_horizon_seconds": 0.05},
            ))
            await db.commit()
            await db.refresh(contest)
            return contest

    import asyncio
    contest = asyncio.run(create_private_contest_with_obs())

    _, member_headers = create_user_and_headers(
        client, admin_headers, "member_lb", "member_lb@example.com", "pass"
    )

    async def invite_member():
        async with db_factory() as db:
            admin_result = await db.execute(select(User).where(User.username == "admin1"))
            admin = admin_result.scalar_one()
            db.add(Invitation(
                email="member_lb@example.com",
                contest_id=contest.id,
                invited_by=admin.id,
            ))
            await db.commit()

    asyncio.run(invite_member())
    register(client, member_headers, str(contest.id))

    response = client.get(
        f"/api/v1/contests/{contest.id}/leaderboard",
        headers=member_headers,
    )

    assert response.status_code == 200


def test_update_leaderboard_honours_maximize_direction(client, db_factory):
    """Regression: with a maximize metric the best (highest) score must win
    rank 1 and a participant's lower new score must not replace their best."""
    import uuid

    from epic.api.routers.submissions import _update_leaderboard
    from epic.core.db.models import LeaderboardEntry
    from sqlalchemy import select

    contest_id = uuid.uuid4()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    sub_1, sub_2, sub_3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async def run_updates():
        await _update_leaderboard(contest_id, user_a, sub_1, 0.4, "maximize", db_factory)
        await _update_leaderboard(contest_id, user_b, sub_2, 0.9, "maximize", db_factory)
        # user_a submits a worse (lower) score: must NOT replace their 0.4
        await _update_leaderboard(contest_id, user_a, sub_3, 0.2, "maximize", db_factory)
        async with db_factory() as db:
            result = await db.execute(
                select(LeaderboardEntry)
                .where(LeaderboardEntry.contest_id == contest_id)
                .order_by(LeaderboardEntry.rank.asc())
            )
            return list(result.scalars())

    entries = asyncio.run(run_updates())

    assert len(entries) == 2
    assert entries[0].user_id == user_b          # highest score ranks first
    assert entries[0].rank == 1
    assert entries[0].score == 0.9
    assert entries[1].user_id == user_a
    assert entries[1].rank == 2
    assert entries[1].score == 0.4               # best kept, 0.2 discarded


def test_update_leaderboard_honours_minimize_direction(client, db_factory):
    """With a minimize metric (e.g. MAE) the lowest score wins rank 1."""
    import uuid

    from epic.api.routers.submissions import _update_leaderboard
    from epic.core.db.models import LeaderboardEntry
    from sqlalchemy import select

    contest_id = uuid.uuid4()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    async def run_updates():
        await _update_leaderboard(contest_id, user_a, uuid.uuid4(), 0.4, "minimize", db_factory)
        await _update_leaderboard(contest_id, user_b, uuid.uuid4(), 0.1, "minimize", db_factory)
        async with db_factory() as db:
            result = await db.execute(
                select(LeaderboardEntry)
                .where(LeaderboardEntry.contest_id == contest_id)
                .order_by(LeaderboardEntry.rank.asc())
            )
            return list(result.scalars())

    entries = asyncio.run(run_updates())

    assert entries[0].user_id == user_b          # lowest score ranks first
    assert entries[0].score == 0.1
    assert entries[1].user_id == user_a
