import asyncio
from datetime import datetime, timedelta, timezone

from epic_core.db.models import Contest, SimulationSession


async def _create_contest(db_factory, name: str = "API Contest") -> Contest:
    async with db_factory() as db:
        contest = Contest(
            name=name,
            twin_id="mechanical_system",
            scenario_id="normal_operation",
            sampling_rate_hz=10.0,
            end_date=datetime.now(timezone.utc) + timedelta(seconds=1),
        )
        db.add(contest)
        await db.commit()
        await db.refresh(contest)
        return contest


async def _create_session(db_factory, contest: Contest) -> SimulationSession:
    async with db_factory() as db:
        session = SimulationSession(
            contest_id=contest.id,
            twin_id=contest.twin_id,
            scenario_id=contest.scenario_id,
            sampling_rate_hz=contest.sampling_rate_hz,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session


def test_get_contest_session_with_no_session_returns_404(
    client, auth_headers, db_factory
):
    contest = asyncio.run(_create_contest(db_factory, name="No Session Contest"))

    response = client.get(
        f"/api/v1/contests/{contest.id}/session",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_get_contest_session_after_session_created_returns_200(
    client, auth_headers, db_factory
):
    contest = asyncio.run(_create_contest(db_factory, name="Session Contest"))
    session = asyncio.run(_create_session(db_factory, contest))

    response = client.get(
        f"/api/v1/contests/{contest.id}/session",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == str(session.id)
    assert body["contest_id"] == str(contest.id)
    assert body["twin_id"] == "mechanical_system"
    assert body["scenario_id"] == "normal_operation"
    assert body["sampling_rate_hz"] == 10.0
    assert body["status"] == "CREATED"
    assert body["started_at"] is None
    assert body["ended_at"] is None


def test_get_nonexistent_contest_session_returns_404(client, auth_headers):
    response = client.get(
        "/api/v1/contests/00000000-0000-0000-0000-000000000001/session",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONTEST_NOT_FOUND"
