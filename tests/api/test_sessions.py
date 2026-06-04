import asyncio
from uuid import UUID

from epic_core.db.models import SimulationSession
from epic_core.engine import SimulationEngine


def _create_session(client, auth_headers, **overrides):
    payload = {
        "twin_id": "mechanical_system",
        "scenario_id": "normal_operation",
        "mode": "TRAINING",
        "duration_seconds": 0.1,
        "sampling_rate_hz": 10.0,
        "seed": None,
    }
    payload.update(overrides)
    return client.post("/api/v1/sessions", json=payload, headers=auth_headers)


def test_create_session_returns_201_with_fields(client, auth_headers):
    response = _create_session(client, auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["twin_id"] == "mechanical_system"
    assert body["scenario_id"] == "normal_operation"
    assert body["mode"] == "TRAINING"
    assert body["sampling_rate_hz"] == 10.0
    assert body["duration_seconds"] == 0.1


def test_create_session_without_auth_returns_401(client):
    response = client.post(
        "/api/v1/sessions",
        json={
            "twin_id": "mechanical_system",
            "scenario_id": "normal_operation",
            "mode": "TRAINING",
            "duration_seconds": 0.1,
            "sampling_rate_hz": 10.0,
            "seed": None,
        },
    )

    assert response.status_code == 401


def test_create_session_with_unknown_twin_returns_404(client, auth_headers):
    response = _create_session(client, auth_headers, twin_id="unknown")

    assert response.status_code == 404


def test_get_session_returns_session(client, auth_headers):
    created = _create_session(client, auth_headers).json()

    response = client.get(f"/api/v1/sessions/{created['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_session_for_another_user_returns_403(client, auth_headers):
    other_user = client.post(
        "/api/v1/users",
        json={
            "username": "other",
            "email": "other@example.com",
            "password": "correct-password",
        },
    ).json()
    other_login = client.post(
        "/api/v1/auth/login",
        json={"username": other_user["username"], "password": "correct-password"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other_login['access_token']}"}
    created = _create_session(client, other_headers).json()

    response = client.get(f"/api/v1/sessions/{created['id']}", headers=auth_headers)

    assert response.status_code == 403


async def _create_session_record(db_factory, user_id: str) -> SimulationSession:
    async with db_factory() as db:
        session = SimulationSession(
            user_id=UUID(user_id),
            twin_id="mechanical_system",
            scenario_id="normal_operation",
            mode="TRAINING",
            duration_seconds=1.0,
            sampling_rate_hz=10.0,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session


def test_get_session_observations_returns_list(
    client, auth_headers, registered_user, db_factory
):
    session = asyncio.run(_create_session_record(db_factory, registered_user["id"]))
    asyncio.run(SimulationEngine().run_session(str(session.id), db_factory))

    response = client.get(
        f"/api/v1/sessions/{session.id}/observations",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == str(session.id)
    assert body["total"] > 0
    assert isinstance(body["observations"], list)
    assert "position" in body["observations"][0]["sensors"]
