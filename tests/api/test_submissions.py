import asyncio
import time
from datetime import datetime, timedelta, timezone

from epic_core.db.models import Contest, SensorObservation, SimulationSession


def submission_payload(sequence_id: int = 1) -> dict:
    return {
        "task_id": "forecasting",
        "prediction_from_sequence": sequence_id,
        "payload": {
            "forecast": {
                "horizon_1": {"position": 0.12},
                "horizon_5": {"position": 0.24},
            }
        },
    }


def create_user_and_headers(client, username: str, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/users",
        json={"username": username, "email": email, "password": password},
    )
    assert response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def create_contest_with_observation(db_factory, name: str, status: str = "ACTIVE"):
    async def create_records():
        now = datetime.now(timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name=name,
                description="Submission test contest",
                status=status,
                visibility="PUBLIC",
                twin_id="mechanical_system",
                scenario_id="normal_operation",
                sampling_rate_hz=20.0,
                start_date=now,
                end_date=now + timedelta(seconds=10),
                created_by="admin1",
            )
            db.add(contest)
            await db.commit()
            await db.refresh(contest)

            session = SimulationSession(
                contest_id=contest.id,
                twin_id=contest.twin_id,
                scenario_id=contest.scenario_id,
                sampling_rate_hz=contest.sampling_rate_hz,
                status="RUNNING",
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)

            observation = SensorObservation(
                session_id=session.id,
                sequence_id=1,
                timestamp=datetime.now(timezone.utc) - timedelta(seconds=1),
                sensors={"position": 0.1},
                labels=None,
            )
            db.add(observation)
            await db.commit()
            return contest

    return asyncio.run(create_records())


def register_participant(client, auth_headers, contest_id: str) -> None:
    response = client.post(
        "/api/v1/contest-registrations",
        json={"contest_id": contest_id},
        headers=auth_headers,
    )
    assert response.status_code == 201


def submit(client, auth_headers, contest_id: str, sequence_id: int = 1):
    return client.post(
        f"/api/v1/contests/{contest_id}/submissions",
        json=submission_payload(sequence_id),
        headers=auth_headers,
    )


def create_scoring_contest(db_factory):
    async def create_records():
        now = datetime.now(timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name="Scored submission contest",
                description="Scoring test contest",
                status="ACTIVE",
                visibility="PUBLIC",
                twin_id="mechanical_system",
                scenario_id="normal_operation",
                sampling_rate_hz=20.0,
                task_type="FORECASTING",
                forecast_horizons=[1],
                start_date=now,
                end_date=now + timedelta(seconds=10),
                created_by="admin1",
            )
            db.add(contest)
            await db.commit()
            await db.refresh(contest)

            session = SimulationSession(
                contest_id=contest.id,
                twin_id=contest.twin_id,
                scenario_id=contest.scenario_id,
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


def scored_submission_payload() -> dict:
    return {
        "task_id": "forecasting",
        "prediction_from_sequence": 1,
        "payload": {
            "forecast": {
                "horizon_1": {"position": 0.25},
            }
        },
    }


def create_scored_submission(client, db_factory, auth_headers):
    contest = create_scoring_contest(db_factory)
    register_participant(client, auth_headers, str(contest.id))
    response = client.post(
        f"/api/v1/contests/{contest.id}/submissions",
        json=scored_submission_payload(),
        headers=auth_headers,
    )
    assert response.status_code == 201
    return contest, response.json()


def wait_for_evaluated_submission(client, auth_headers, submission_id: str) -> dict:
    for _ in range(20):
        response = client.get(f"/api/v1/submissions/{submission_id}", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        if body["status"] == "EVALUATED":
            return body
        time.sleep(0.05)
    return body


def test_post_valid_submission_returns_pending(
    client, db_factory, auth_headers, registered_user
):
    contest = create_contest_with_observation(db_factory, "Valid submission")
    register_participant(client, auth_headers, str(contest.id))

    response = submit(client, auth_headers, str(contest.id))

    assert response.status_code == 201
    body = response.json()
    assert body["contest_id"] == str(contest.id)
    assert body["user_id"] == registered_user["id"]
    assert body["status"] == "PENDING"


def test_post_by_unregistered_participant_returns_409(client, db_factory, auth_headers):
    contest = create_contest_with_observation(db_factory, "Unregistered submission")

    response = submit(client, auth_headers, str(contest.id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REGISTRATION_ERROR"


def test_post_on_non_active_contest_returns_409(client, db_factory, auth_headers):
    contest = create_contest_with_observation(
        db_factory, "Non active submission", status="SCHEDULED"
    )

    response = submit(client, auth_headers, str(contest.id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTEST_STATE_ERROR"


def test_post_with_nonexistent_prediction_sequence_returns_422(
    client, db_factory, auth_headers
):
    contest = create_contest_with_observation(db_factory, "Missing anchor submission")
    register_participant(client, auth_headers, str(contest.id))

    response = submit(client, auth_headers, str(contest.id), sequence_id=999)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SUBMISSION_ERROR"


def test_get_contest_submissions_returns_only_own_submissions(
    client, db_factory, auth_headers
):
    contest = create_contest_with_observation(db_factory, "Own submissions list")
    register_participant(client, auth_headers, str(contest.id))
    own_response = submit(client, auth_headers, str(contest.id))
    assert own_response.status_code == 201

    other_headers = create_user_and_headers(
        client, "student2", "student2-submissions@example.com", "other-password"
    )
    register_participant(client, other_headers, str(contest.id))
    other_response = submit(client, other_headers, str(contest.id))
    assert other_response.status_code == 201

    response = client.get(
        f"/api/v1/contests/{contest.id}/submissions", headers=auth_headers
    )

    assert response.status_code == 200
    submissions = response.json()["submissions"]
    submission_ids = {submission["submission_id"] for submission in submissions}
    assert own_response.json()["submission_id"] in submission_ids
    assert other_response.json()["submission_id"] not in submission_ids


def test_get_submission_returns_submission_for_owner(client, db_factory, auth_headers):
    contest = create_contest_with_observation(db_factory, "Get owned submission")
    register_participant(client, auth_headers, str(contest.id))
    submission_response = submit(client, auth_headers, str(contest.id))
    assert submission_response.status_code == 201

    response = client.get(
        f"/api/v1/submissions/{submission_response.json()['submission_id']}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["submission_id"] == submission_response.json()["submission_id"]
    assert body["payload"] == submission_payload()["payload"]


def test_get_submission_by_different_user_returns_403(
    client, db_factory, auth_headers
):
    contest = create_contest_with_observation(db_factory, "Denied submission")
    register_participant(client, auth_headers, str(contest.id))
    submission_response = submit(client, auth_headers, str(contest.id))
    assert submission_response.status_code == 201
    other_headers = create_user_and_headers(
        client, "student3", "student3-submissions@example.com", "other-password"
    )

    response = client.get(
        f"/api/v1/submissions/{submission_response.json()['submission_id']}",
        headers=other_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_scored_submission_eventually_becomes_evaluated(
    client, db_factory, auth_headers
):
    _contest, submission = create_scored_submission(client, db_factory, auth_headers)

    body = wait_for_evaluated_submission(
        client, auth_headers, submission["submission_id"]
    )

    assert body["status"] == "EVALUATED"


def test_get_submission_scores_returns_mae_score(client, db_factory, auth_headers):
    _contest, submission = create_scored_submission(client, db_factory, auth_headers)
    body = wait_for_evaluated_submission(
        client, auth_headers, submission["submission_id"]
    )
    assert body["status"] == "EVALUATED"

    response = client.get(
        f"/api/v1/submissions/{submission['submission_id']}/scores",
        headers=auth_headers,
    )

    assert response.status_code == 200
    scores = response.json()["scores"]
    assert scores
    mae_scores = [score for score in scores if score["metric_id"] == "mae"]
    assert mae_scores
    assert isinstance(mae_scores[0]["value"], float)
    assert mae_scores[0]["value"] >= 0.0


def test_score_details_contain_per_sensor_breakdown(
    client, db_factory, auth_headers
):
    _contest, submission = create_scored_submission(client, db_factory, auth_headers)
    body = wait_for_evaluated_submission(
        client, auth_headers, submission["submission_id"]
    )
    assert body["status"] == "EVALUATED"

    response = client.get(
        f"/api/v1/submissions/{submission['submission_id']}/scores",
        headers=auth_headers,
    )

    assert response.status_code == 200
    score = response.json()["scores"][0]
    assert score["details"]["sensor_id"] == "position"
    assert score["details"]["horizons"]["horizon_1"]["y_true"] == 0.2
    assert score["details"]["horizons"]["horizon_1"]["y_pred"] == 0.25
