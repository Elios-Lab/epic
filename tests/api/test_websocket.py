import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from starlette.websockets import WebSocketDisconnect

from epic_core.db.models import Contest


async def _create_contest(
    db_factory,
    name: str,
    status: str = "ACTIVE",
) -> Contest:
    async with db_factory() as db:
        contest = Contest(
            name=name,
            status=status,
            twin_id="mass_spring_damper",
            sensor_configs=[{"sensor_id": "position"}],
            sampling_rate_hz=10.0,
            end_date=datetime.now(timezone.utc) + timedelta(seconds=1),
        )
        db.add(contest)
        await db.commit()
        await db.refresh(contest)
        return contest


def _token(auth_headers) -> str:
    return auth_headers["Authorization"].split(" ", 1)[1]


def test_websocket_rejects_missing_token(client, db_factory):
    contest = asyncio.run(_create_contest(db_factory, "missing-token"))

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/ws/contests/{contest.id}"):
            pass


def test_websocket_rejects_invalid_token(client, db_factory):
    contest = asyncio.run(_create_contest(db_factory, "invalid-token"))

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            f"/api/v1/ws/contests/{contest.id}?token=invalid-token"
        ):
            pass

    assert exc_info.value.code == 1008


def test_websocket_rejects_nonexistent_contest(client, auth_headers):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/api/v1/ws/contests/00000000-0000-0000-0000-000000000001"
            f"?token={_token(auth_headers)}"
        ):
            pass

    assert exc_info.value.code == 1008


def test_websocket_rejects_non_active_contest(client, auth_headers, db_factory):
    contest = asyncio.run(
        _create_contest(db_factory, "non-active", status="DRAFT")
    )

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            f"/api/v1/ws/contests/{contest.id}?token={_token(auth_headers)}"
        ):
            pass

    assert exc_info.value.code == 1008


def _register(client, auth_headers, contest_id) -> None:
    response = client.post(
        "/api/v1/contest-registrations",
        json={"contest_id": str(contest_id)},
        headers=auth_headers,
    )
    assert response.status_code == 201


def test_websocket_rejects_unregistered_participant(client, auth_headers, db_factory):
    """A participant without an active registration must not receive the stream."""
    contest = asyncio.run(_create_contest(db_factory, "unregistered-participant"))

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            f"/api/v1/ws/contests/{contest.id}?token={_token(auth_headers)}"
        ):
            pass

    assert exc_info.value.code == 1008


def test_websocket_allows_admin_without_registration(client, admin_headers, db_factory):
    """Administrators may monitor any active contest stream."""
    contest = asyncio.run(_create_contest(db_factory, "admin-monitor"))
    payload = {"sequence_id": 1, "sensors": {"position": 0.1}}

    with client.websocket_connect(
        f"/api/v1/ws/contests/{contest.id}?token={_token(admin_headers)}"
    ) as websocket:
        broadcaster = client.app.state.broadcaster
        asyncio.run(broadcaster.broadcast(str(contest.id), payload))

        assert websocket.receive_json() == payload


def test_websocket_delivers_broadcast_message(client, auth_headers, db_factory):
    contest = asyncio.run(_create_contest(db_factory, "active-broadcast"))
    _register(client, auth_headers, contest.id)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sequence_id": 1,
        "sensors": {"position": 0.1},
    }

    with client.websocket_connect(
        f"/api/v1/ws/contests/{contest.id}?token={_token(auth_headers)}"
    ) as websocket:
        broadcaster = client.app.state.broadcaster
        asyncio.run(broadcaster.broadcast(str(contest.id), payload))

        assert websocket.receive_json() == payload
