"""Tests for server-restart recovery logic (_recover_after_restart)."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select

from epic_api.main import _recover_after_restart
from epic_core.notifications import NullNotificationService
from epic_core.db.models import Contest, SimulationSession, Submission, Task
from epic_core.db.session import get_session_factory


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


async def _create_active_contest_with_running_session(db_factory, name: str) -> tuple:
    """Insert an ACTIVE contest whose session is stuck in RUNNING (simulating a crash)."""
    async with db_factory() as db:
        now = _now()
        contest = Contest(
            name=name,
            status="ACTIVE",
            visibility="PUBLIC",
            twin_id="mass_spring_damper",
            sensor_configs=[{"sensor_id": "position"}],
            sampling_rate_hz=20.0,
            start_date=now - timedelta(seconds=10),
            end_of_observation=now - timedelta(seconds=2),
            prediction_horizon_seconds=0.1,
            end_date=now + timedelta(seconds=60),
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
            configuration={"eval_steps": 1, "prediction_horizon_seconds": 0.1},
        ))
        session = SimulationSession(
            contest_id=contest.id,
            twin_id=contest.twin_id,
            sampling_rate_hz=contest.sampling_rate_hz,
            status="RUNNING",                    # stuck — engine died
            started_at=now - timedelta(seconds=5),
        )
        db.add(session)
        await db.commit()
        await db.refresh(contest)
        await db.refresh(session)
        return contest, session


async def _get_any_user_id(db_factory):
    from epic_core.db.models import User
    async with db_factory() as db:
        result = await db.execute(select(User).limit(1))
        return result.scalar_one().id


async def _create_pending_submission(db_factory, contest_id: UUID) -> Submission:
    """Insert a PENDING submission (its scoring task was lost on crash)."""
    user_id = await _get_any_user_id(db_factory)
    async with db_factory() as db:
        sub = Submission(
            contest_id=contest_id,
            user_id=user_id,
            task_id="forecasting",
            payload={"forecast": {"position": [0.1]}},
            status="PENDING",
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
        return sub


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_orphaned_running_session_is_paused(client, db_factory):
    """A RUNNING session whose engine died must be paused, not left as zombie."""
    contest, session = asyncio.run(
        _create_active_contest_with_running_session(db_factory, "Zombie Contest")
    )

    asyncio.run(_recover_after_restart(NullNotificationService()))

    async def load():
        async with db_factory() as db:
            c = (await db.execute(select(Contest).where(Contest.id == contest.id))).scalar_one()
            s = (await db.execute(select(SimulationSession).where(SimulationSession.id == session.id))).scalar_one()
            return c, s

    recovered_contest, recovered_session = asyncio.run(load())

    assert recovered_contest.status == "PAUSED"
    assert recovered_session.status == "PAUSED"
    assert recovered_session.ended_at is not None
    assert "recovery" in (recovered_session.session_metadata or {})


def test_orphaned_created_session_is_paused(client, db_factory):
    """A CREATED session (crash before engine started) is also paused."""
    async def create_created_session():
        async with db_factory() as db:
            now = _now()
            contest = Contest(
                name="Pre-start Zombie Contest",
                status="ACTIVE",
                visibility="PUBLIC",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=20.0,
                start_date=now - timedelta(seconds=10),
                end_of_observation=now - timedelta(seconds=2),
                prediction_horizon_seconds=0.1,
                end_date=now + timedelta(seconds=60),
                created_by=None,
            )
            db.add(contest)
            await db.flush()
            session = SimulationSession(
                contest_id=contest.id,
                twin_id=contest.twin_id,
                sampling_rate_hz=contest.sampling_rate_hz,
                status="CREATED",                # never even started
            )
            db.add(session)
            await db.commit()
            await db.refresh(contest)
            await db.refresh(session)
            return contest, session

    contest, session = asyncio.run(create_created_session())
    asyncio.run(_recover_after_restart(NullNotificationService()))

    async def load():
        async with db_factory() as db:
            c = (await db.execute(select(Contest).where(Contest.id == contest.id))).scalar_one()
            s = (await db.execute(select(SimulationSession).where(SimulationSession.id == session.id))).scalar_one()
            return c, s

    c, s = asyncio.run(load())
    assert c.status == "PAUSED"
    assert s.status == "PAUSED"


def test_non_active_contest_session_left_unchanged(client, db_factory):
    """Sessions belonging to non-ACTIVE contests are not touched."""
    async def create():
        async with db_factory() as db:
            now = _now()
            contest = Contest(
                name="Closed Contest",
                status="CLOSED",
                visibility="PUBLIC",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=20.0,
                start_date=now - timedelta(seconds=20),
                end_of_observation=now - timedelta(seconds=15),
                prediction_horizon_seconds=0.1,
                end_date=now - timedelta(seconds=5),
                created_by=None,
            )
            db.add(contest)
            await db.flush()
            session = SimulationSession(
                contest_id=contest.id,
                twin_id=contest.twin_id,
                sampling_rate_hz=contest.sampling_rate_hz,
                status="RUNNING",
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            return contest, session

    contest, session = asyncio.run(create())
    asyncio.run(_recover_after_restart(NullNotificationService()))

    async def load():
        async with db_factory() as db:
            s = (await db.execute(select(SimulationSession).where(SimulationSession.id == session.id))).scalar_one()
            return s

    s = asyncio.run(load())
    assert s.status == "RUNNING"  # not touched


def test_pending_submission_requeued(client, db_factory):
    """_recover_after_restart must call asyncio.create_task for every PENDING submission."""
    from unittest.mock import MagicMock, patch

    contest, _ = asyncio.run(
        _create_active_contest_with_running_session(db_factory, "Submission Recovery Contest")
    )
    sub = asyncio.run(_create_pending_submission(db_factory, contest.id))

    created_coros = []

    def capture_create_task(coro, **kwargs):
        created_coros.append(coro)
        # Return a dummy future so the caller doesn't break.
        coro.close()  # discard cleanly to avoid ResourceWarning
        f = asyncio.get_event_loop().create_future()
        f.set_result(None)
        return f

    with patch("epic_api.main.asyncio.create_task", side_effect=capture_create_task):
        asyncio.run(_recover_after_restart(NullNotificationService()))

    assert len(created_coros) >= 1, "Expected at least one create_task call for the PENDING submission"


def test_already_paused_contest_left_unchanged(client, db_factory):
    """A PAUSED contest with a PAUSED session is not double-touched."""
    async def create():
        async with db_factory() as db:
            now = _now()
            contest = Contest(
                name="Already Paused Contest",
                status="PAUSED",
                visibility="PUBLIC",
                twin_id="mass_spring_damper",
                sensor_configs=[{"sensor_id": "position"}],
                sampling_rate_hz=20.0,
                start_date=now - timedelta(seconds=10),
                end_of_observation=now + timedelta(seconds=30),
                prediction_horizon_seconds=1.0,
                end_date=now + timedelta(seconds=60),
                created_by=None,
            )
            db.add(contest)
            await db.flush()
            session = SimulationSession(
                contest_id=contest.id,
                twin_id=contest.twin_id,
                sampling_rate_hz=contest.sampling_rate_hz,
                status="PAUSED",
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            return session

    session = asyncio.run(create())
    asyncio.run(_recover_after_restart(NullNotificationService()))

    async def load():
        async with db_factory() as db:
            s = (await db.execute(select(SimulationSession).where(SimulationSession.id == session.id))).scalar_one()
            return s

    s = asyncio.run(load())
    assert s.status == "PAUSED"
    assert "recovery" not in (s.session_metadata or {})
