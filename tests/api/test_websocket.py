import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
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


def _make_organizer(client, admin_headers, db_factory, username: str):
    """Create a user, promote to ORGANIZER, and return (user_id, headers)."""
    from epic_core.db.models import User
    from sqlalchemy import select as sa_select

    response = client.post(
        "/api/v1/users",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "org-password-123",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    user_id = response.json()["id"]

    async def _promote():
        async with db_factory() as db:
            result = await db.execute(sa_select(User).where(User.username == username))
            user = result.scalar_one()
            user.role = "ORGANIZER"
            await db.commit()

    asyncio.run(_promote())

    login = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "org-password-123"},
    )
    assert login.status_code == 200
    return user_id, {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_websocket_allows_organizer_for_own_contest(client, admin_headers, db_factory):
    """The contest owner may monitor their own stream without a registration."""
    from uuid import UUID

    owner_id, owner_headers = _make_organizer(client, admin_headers, db_factory, "ws_owner")
    contest = asyncio.run(_create_contest(db_factory, "organizer-own-stream"))

    async def _set_owner():
        async with db_factory() as db:
            result = await db.execute(select(Contest).where(Contest.id == contest.id))
            db_contest = result.scalar_one()
            db_contest.created_by = UUID(owner_id)
            await db.commit()

    asyncio.run(_set_owner())

    payload = {"sequence_id": 1, "sensors": {"position": 0.1}}
    with client.websocket_connect(
        f"/api/v1/ws/contests/{contest.id}?token={_token(owner_headers)}"
    ) as websocket:
        broadcaster = client.app.state.broadcaster
        asyncio.run(broadcaster.broadcast(str(contest.id), payload))

        assert websocket.receive_json() == payload


def test_websocket_rejects_organizer_for_other_contest(client, admin_headers, db_factory):
    """An organizer must not monitor a contest they do not own."""
    from uuid import UUID

    owner_id, _ = _make_organizer(client, admin_headers, db_factory, "ws_owner2")
    _, other_headers = _make_organizer(client, admin_headers, db_factory, "ws_other")
    contest = asyncio.run(_create_contest(db_factory, "organizer-foreign-stream"))

    async def _set_owner():
        async with db_factory() as db:
            result = await db.execute(select(Contest).where(Contest.id == contest.id))
            db_contest = result.scalar_one()
            db_contest.created_by = UUID(owner_id)
            await db.commit()

    asyncio.run(_set_owner())

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            f"/api/v1/ws/contests/{contest.id}?token={_token(other_headers)}"
        ):
            pass

    assert exc_info.value.code == 1008
