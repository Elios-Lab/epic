import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from epic_core.kernel.db.models import SensorObservation, SimulationSession


def _token(headers: dict) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def _create_and_activate_contest(client, admin_headers) -> dict:
    now = datetime.now(timezone.utc)
    response = client.post(
        "/api/v1/contests",
        json={
            "name": "E2E contest stream",
            "description": "End-to-end streaming contest",
            "visibility": "PUBLIC",
            "twin_id": "mass_spring_damper",
            "sensor_configs": [{"sensor_id": "position"}],
            "fault_schedule": [],
            "initial_conditions": {"position": 0.1},
            "sampling_rate_hz": 10.0,
            "start_date": now.isoformat(),
            "end_of_observation": (now + timedelta(seconds=60)).isoformat(),
            "prediction_horizon_seconds": 1.0,
            "end_date": (now + timedelta(seconds=120)).isoformat(),
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    contest = response.json()

    response = client.patch(
        f"/api/v1/contests/{contest['contest_id']}",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"
    asyncio.run(asyncio.sleep(0.5))
    return response.json()


def _receive_json_with_timeout(websocket, timeout: float = 5.0):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(websocket.receive_json)
    try:
        return "message", future.result(timeout=timeout)
    except WebSocketDisconnect as exc:
        return "disconnect", exc
    except TimeoutError:
        return "timeout", None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _must_receive_json(websocket, timeout: float = 5.0) -> dict:
    outcome, payload = _receive_json_with_timeout(websocket, timeout)
    if outcome != "message":
        raise AssertionError(f"expected websocket message, got {outcome}")
    return payload


async def _wait_for_observation(db_factory, contest_id: str, sequence_id: int) -> None:
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        async with db_factory() as db:
            result = await db.execute(
                select(SensorObservation)
                .join(
                    SimulationSession,
                    SensorObservation.session_id == SimulationSession.id,
                )
                .where(
                    SimulationSession.contest_id == UUID(contest_id),
                    SensorObservation.sequence_id == sequence_id,
                )
            )
            if result.scalar_one_or_none() is not None:
                return
        await asyncio.sleep(0.1)
    raise AssertionError(f"observation {sequence_id} was not persisted")


def test_e2e_contest_creates_and_streams_observations(
    client, admin_headers, auth_headers, db_factory
):
    contest = _create_and_activate_contest(client, admin_headers)
    contest_id = contest["contest_id"]

    response = client.post(
        "/api/v1/contest-registrations",
        json={"contest_id": contest_id},
        headers=auth_headers,
    )
    assert response.status_code == 201

    received = []
    with client.websocket_connect(
        f"/api/v1/ws/contests/{contest_id}?token={_token(auth_headers)}"
    ) as websocket:
        for _ in range(3):
            received.append(_must_receive_json(websocket))

    sequence_ids = [message["sequence_id"] for message in received]
    assert sequence_ids == sorted(sequence_ids)
    assert len(set(sequence_ids)) == len(sequence_ids)
    for message in received:
        assert {"sequence_id", "timestamp", "sensors"} <= message.keys()
        assert "position" in message["sensors"]
        assert isinstance(message["sensors"]["position"], float)

    assert received[-1]["sequence_id"] >= 3


def test_e2e_websocket_disconnects_when_contest_closed(
    client, admin_headers, auth_headers
):
    contest = _create_and_activate_contest(client, admin_headers)
    contest_id = contest["contest_id"]

    response = client.post(
        "/api/v1/contest-registrations",
        json={"contest_id": contest_id},
        headers=auth_headers,
    )
    assert response.status_code == 201

    with client.websocket_connect(
        f"/api/v1/ws/contests/{contest_id}?token={_token(auth_headers)}"
    ) as websocket:
        message = _must_receive_json(websocket)
        assert "position" in message["sensors"]

        while message["sequence_id"] < 95:
            message = _must_receive_json(websocket)

        response = client.patch(
            f"/api/v1/contests/{contest_id}",
            json={"status": "CLOSED"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CLOSED"

        deadline = time.monotonic() + 3.0
        stopped = False
        while time.monotonic() < deadline:
            outcome, message = _receive_json_with_timeout(websocket, timeout=0.25)
            if outcome in {"disconnect", "timeout"}:
                stopped = True
                break

        assert stopped
