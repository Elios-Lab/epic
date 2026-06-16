import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

from epic_core.kernel.db.models import Contest, SensorObservation, SimulationSession, Task


# Two-phase test contests use a very short eval window that is already in the past,
# so submissions are accepted immediately without waiting.
_EVAL_STEPS = 1         # round(0.05 s * 20 Hz) = 1
_PREDICTION_HORIZON = 0.05
_SAMPLING_RATE = 20.0


def submission_payload() -> dict:
    return {
        "task_id": "forecasting",
        "payload": {
            "forecast": {"position": [0.12]},
        },
    }


def create_user_and_headers(
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


def create_contest_with_observation(db_factory, name: str, status: str = "ACTIVE"):
    async def create_records():
        now = datetime.now(timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name=name,
                description="Submission test contest",
                status=status,
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


def submit(client, auth_headers, contest_id: str):
    return client.post(
        f"/api/v1/contests/{contest_id}/submissions",
        json=submission_payload(),
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

            # Provide enough observations to satisfy eval_steps
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
        "payload": {
            "forecast": {"position": [0.25]},
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


def test_post_on_non_two_phase_contest_returns_409(client, db_factory, auth_headers):
    """Regression: a contest without end_of_observation must reject submissions
    with a clean validation error, not crash with a 500."""

    async def create_records():
        now = datetime.now(timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name="Non two-phase submission",
                description="Classic contest without evaluation window",
                status="ACTIVE",
                visibility="PUBLIC",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=_SAMPLING_RATE,
                start_date=now - timedelta(seconds=10),
                end_date=now + timedelta(seconds=30),
                end_of_observation=None,
                prediction_horizon_seconds=None,
                created_by=None,
            )
            db.add(contest)
            await db.commit()
            await db.refresh(contest)
            return contest

    contest = asyncio.run(create_records())
    register_participant(client, auth_headers, str(contest.id))

    response = submit(client, auth_headers, str(contest.id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTEST_STATE_ERROR"
    assert "two-phase" in response.json()["error"]["message"]


def test_get_contest_submissions_returns_only_own_submissions(
    client, db_factory, auth_headers, admin_headers
):
    contest = create_contest_with_observation(db_factory, "Own submissions list")
    register_participant(client, auth_headers, str(contest.id))
    own_response = submit(client, auth_headers, str(contest.id))
    assert own_response.status_code == 201

    other_headers = create_user_and_headers(
        client,
        admin_headers,
        "student2",
        "student2-submissions@example.com",
        "other-password",
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
    client, db_factory, auth_headers, admin_headers
):
    contest = create_contest_with_observation(db_factory, "Denied submission")
    register_participant(client, auth_headers, str(contest.id))
    submission_response = submit(client, auth_headers, str(contest.id))
    assert submission_response.status_code == 201
    other_headers = create_user_and_headers(
        client,
        admin_headers,
        "student3",
        "student3-submissions@example.com",
        "other-password",
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
    assert score["details"]["eval_steps"] == _EVAL_STEPS
    # Without ground_truth in the DB fixture the scorer falls back to sensors.
    assert score["details"]["scored_against"] in ("sensors", "ground_truth")


def test_scoring_uses_only_target_variables(client, db_factory, auth_headers):
    async def create_targeted_contest():
        now = datetime.now(timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name="Target variable scoring contest",
                status="ACTIVE",
                visibility="PUBLIC",
                twin_id="mass_spring_damper",
                sensor_configs=[
                    {"sensor_id": "position"},
                    {"sensor_id": "velocity"},
                ],
                sampling_rate_hz=_SAMPLING_RATE,
                start_date=now - timedelta(seconds=10),
                end_date=now + timedelta(seconds=30),
                end_of_observation=now - timedelta(seconds=2),
                prediction_horizon_seconds=_PREDICTION_HORIZON,
                created_by=None,
            )
            db.add(contest)
            await db.flush()
            db.add(Task(
                contest_id=contest.id,
                task_type="FORECASTING",
                name="FORECASTING",
                metric_ids=["mae"],
                weight=1.0,
                configuration={
                    "eval_steps": _EVAL_STEPS,
                    "prediction_horizon_seconds": _PREDICTION_HORIZON,
                    "target_variables": ["position"],
                },
            ))
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

            db.add(SensorObservation(
                session_id=session.id,
                sequence_id=1,
                timestamp=now - timedelta(seconds=1),
                sensors={"position": 0.1, "velocity": 100.0},
                ground_truth={"position": 0.1, "velocity": 100.0},
                labels=None,
            ))
            await db.commit()
            return contest

    contest = asyncio.run(create_targeted_contest())
    register_participant(client, auth_headers, str(contest.id))

    response = client.post(
        f"/api/v1/contests/{contest.id}/submissions",
        json={
            "task_id": "forecasting",
            "payload": {
                "forecast": {
                    "position": [0.1],
                    "velocity": [-999.0],
                }
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    submission = response.json()

    body = wait_for_evaluated_submission(
        client, auth_headers, submission["submission_id"]
    )
    assert body["status"] == "EVALUATED"

    scores_resp = client.get(
        f"/api/v1/submissions/{submission['submission_id']}/scores",
        headers=auth_headers,
    )
    assert scores_resp.status_code == 200
    scores = scores_resp.json()["scores"]
    assert len(scores) == 1
    assert scores[0]["details"]["sensor_id"] == "position"
    assert scores[0]["value"] == pytest.approx(0.0)


def test_task_id_not_belonging_to_contest_returns_422(
    client, db_factory, auth_headers
):
    contest = create_contest_with_observation(db_factory, "Wrong task id contest")
    register_participant(client, auth_headers, str(contest.id))

    response = client.post(
        f"/api/v1/contests/{contest.id}/submissions",
        json={
            "task_id": "anomaly_detection",
            "payload": {"forecast": {"position": [0.1]}},
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SUBMISSION_ERROR"


def test_scoring_uses_ground_truth_when_present(client, db_factory, auth_headers):
    """When ground_truth is populated the scorer uses it instead of sensors."""
    async def create_gt_contest():
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name="Ground truth scoring contest",
                status="ACTIVE",
                visibility="PUBLIC",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=_SAMPLING_RATE,
                start_date=now - dt.timedelta(seconds=10),
                end_date=now + dt.timedelta(seconds=30),
                end_of_observation=now - dt.timedelta(seconds=2),
                prediction_horizon_seconds=_PREDICTION_HORIZON,
                created_by=None,
            )
            db.add(contest)
            await db.flush()
            db.add(Task(
                contest_id=contest.id,
                task_type="FORECASTING",
                name="FORECASTING",
                metric_ids=["mae"],
                weight=1.0,
                configuration={
                    "eval_steps": _EVAL_STEPS,
                    "prediction_horizon_seconds": _PREDICTION_HORIZON,
                    "score_against": "ground_truth",
                },
            ))
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

            # Observation: sensors=noisy, ground_truth=clean.
            db.add(SensorObservation(
                session_id=session.id,
                sequence_id=1,
                timestamp=now - dt.timedelta(seconds=1),
                sensors={"position": 0.5},        # noisy reading
                ground_truth={"position": 1.0},   # true latent value
                labels=None,
            ))
            await db.commit()
            return contest

    contest = asyncio.run(create_gt_contest())
    register_participant(client, auth_headers, str(contest.id))

    response = client.post(
        f"/api/v1/contests/{contest.id}/submissions",
        json={"task_id": "forecasting", "payload": {"forecast": {"position": [1.0]}}},
        headers=auth_headers,
    )
    assert response.status_code == 201
    submission = response.json()

    body = wait_for_evaluated_submission(client, auth_headers, submission["submission_id"])
    assert body["status"] == "EVALUATED"

    scores_resp = client.get(
        f"/api/v1/submissions/{submission['submission_id']}/scores",
        headers=auth_headers,
    )
    assert scores_resp.status_code == 200
    scores = scores_resp.json()["scores"]
    assert scores
    score = scores[0]
    # Scored against ground_truth=1.0 with prediction 1.0 → MAE = 0.0
    assert score["value"] == pytest.approx(0.0)
    assert score["details"]["scored_against"] == "ground_truth"


def test_scoring_falls_back_to_sensors_when_no_ground_truth(client, db_factory, auth_headers):
    """When ground_truth is missing the scorer falls back to sensor readings."""
    async def create_no_gt_contest():
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name="Sensors fallback contest",
                status="ACTIVE",
                visibility="PUBLIC",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=_SAMPLING_RATE,
                start_date=now - dt.timedelta(seconds=10),
                end_date=now + dt.timedelta(seconds=30),
                end_of_observation=now - dt.timedelta(seconds=2),
                prediction_horizon_seconds=_PREDICTION_HORIZON,
                created_by=None,
            )
            db.add(contest)
            await db.flush()
            db.add(Task(
                contest_id=contest.id,
                task_type="FORECASTING",
                name="FORECASTING",
                metric_ids=["mae"],
                weight=1.0,
                configuration={
                    "eval_steps": _EVAL_STEPS,
                    "prediction_horizon_seconds": _PREDICTION_HORIZON,
                    "score_against": "ground_truth",   # requested but unavailable
                },
            ))
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

            db.add(SensorObservation(
                session_id=session.id,
                sequence_id=1,
                timestamp=now - dt.timedelta(seconds=1),
                sensors={"position": 0.2},   # sensor reading is the only reference
                ground_truth=None,            # not populated (old data / direct insert)
                labels=None,
            ))
            await db.commit()
            return contest

    contest = asyncio.run(create_no_gt_contest())
    register_participant(client, auth_headers, str(contest.id))

    response = client.post(
        f"/api/v1/contests/{contest.id}/submissions",
        json={"task_id": "forecasting", "payload": {"forecast": {"position": [0.2]}}},
        headers=auth_headers,
    )
    assert response.status_code == 201

    body = wait_for_evaluated_submission(client, auth_headers, response.json()["submission_id"])
    assert body["status"] == "EVALUATED"

    scores_resp = client.get(
        f"/api/v1/submissions/{response.json()['submission_id']}/scores",
        headers=auth_headers,
    )
    score = scores_resp.json()["scores"][0]
    # Fell back to sensors=0.2, prediction=0.2 → MAE = 0.0
    assert score["value"] == pytest.approx(0.0)
    assert score["details"]["scored_against"] == "sensors"


def test_scoring_uses_task_metric_ids_when_set(client, db_factory, auth_headers):
    """When task.metric_ids is set, scoring uses it instead of the 'mae' default."""
    async def create_f1_contest():
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        async with db_factory() as db:
            contest = Contest(
                name="F1 metric contest",
                status="ACTIVE",
                visibility="PUBLIC",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=_SAMPLING_RATE,
                start_date=now - dt.timedelta(seconds=10),
                end_date=now + dt.timedelta(seconds=60),
                end_of_observation=now - dt.timedelta(seconds=2),
                prediction_horizon_seconds=_PREDICTION_HORIZON,
                created_by=None,
            )
            db.add(contest)
            await db.flush()
            db.add(Task(
                contest_id=contest.id,
                task_type="FORECASTING",
                name="FORECASTING",
                metric_ids=["f1"],
                weight=1.0,
                configuration={"eval_steps": _EVAL_STEPS, "prediction_horizon_seconds": _PREDICTION_HORIZON},
            ))
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

            for seq, pos in ((1, 0.1), (2, 0.2)):
                db.add(SensorObservation(
                    session_id=session.id,
                    sequence_id=seq,
                    timestamp=now - dt.timedelta(seconds=1),
                    sensors={"position": pos},
                    labels=None,
                ))
            await db.commit()
            return contest

    contest = asyncio.run(create_f1_contest())
    register_participant(client, auth_headers, str(contest.id))

    response = client.post(
        f"/api/v1/contests/{contest.id}/submissions",
        json={"task_id": "forecasting", "payload": {"forecast": {"position": [0.25]}}},
        headers=auth_headers,
    )
    assert response.status_code == 201
    submission = response.json()

    body = wait_for_evaluated_submission(client, auth_headers, submission["submission_id"])
    assert body["status"] == "EVALUATED"

    scores_response = client.get(
        f"/api/v1/submissions/{submission['submission_id']}/scores",
        headers=auth_headers,
    )
    assert scores_response.status_code == 200
    scores = scores_response.json()["scores"]
    assert scores
    assert scores[0]["metric_id"] == "f1"
