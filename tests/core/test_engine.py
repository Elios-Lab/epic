import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from epic_core.kernel.db.base import create_all_tables, create_engine
from epic_core.kernel.db.models import Contest, SensorObservation, SimulationSession
from epic_core.kernel.engine import SimulationEngine
from epic_core.kernel.testing import (
    MockSensor,
    MockTwin,
    test_registry_context as registry_context,
)


class FailingTwin(MockTwin):
    def step(self, state, dt):
        raise RuntimeError("step failed")


class NoisyMockSensor(MockSensor):
    def __init__(self, sensor_id: str = "mock_sensor", noise_std: float = 1.0) -> None:
        super().__init__(sensor_id=sensor_id, constant_value=5.0)
        self.noise_std = noise_std

    def observe(self, state, dt: float = 0.0) -> float:
        return float(self._constant_value + np.random.normal(0.0, self.noise_std))


class ConfigurableNoisyMockSensor(NoisyMockSensor):
    def __init__(self, noise_std: float = 0.0) -> None:
        super().__init__(sensor_id="mock_sensor", noise_std=noise_std)


MOCK_FAULT_SCHEDULE = [
    {
        "fault_id": "mock_fault",
        "start_time": 0.0,
        "end_time": None,
        "severity": 0.5,
    }
]


@pytest_asyncio.fixture
async def engine_db_factory():
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_all_tables(engine)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _create_contest_and_session(
    db_factory,
    name: str,
    twin_id: str = "mock_twin",
    sensor_configs: list[dict] | None = None,
    fault_schedule: list[dict] | None = None,
    seed: int | None = None,
    seconds: float = 1.0,
) -> tuple[Contest, SimulationSession]:
    async with db_factory() as db:
        contest = Contest(
            name=name,
            twin_id=twin_id,
            sensor_configs=sensor_configs or [{"sensor_id": "mock_sensor"}],
            fault_schedule=fault_schedule or [],
            sampling_rate_hz=10.0,
            end_date=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        )
        db.add(contest)
        await db.commit()
        await db.refresh(contest)

        session = SimulationSession(
            contest_id=contest.id,
            twin_id=twin_id,
            sampling_rate_hz=10.0,
            seed=seed,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return contest, session


async def _get_session(db_factory, session_id):
    async with db_factory() as db:
        result = await db.execute(
            select(SimulationSession).where(SimulationSession.id == session_id)
        )
        return result.scalar_one()


async def _get_observations(db_factory, session_id):
    async with db_factory() as db:
        result = await db.execute(
            select(SensorObservation)
            .where(SensorObservation.session_id == session_id)
            .order_by(SensorObservation.sequence_id)
        )
        return result.scalars().all()


@pytest.mark.asyncio
async def test_run_session_completes_and_sets_status(engine_db_factory):
    _, session = await _create_contest_and_session(engine_db_factory, "complete")

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    completed = await _get_session(engine_db_factory, session.id)
    assert completed.status == "COMPLETED"


@pytest.mark.asyncio
async def test_run_session_with_past_end_date_completes_without_running(
    engine_db_factory,
):
    """Regression: if end_date is already past when the session starts (e.g.
    after a server restart), the loop never runs and the session must end
    COMPLETED — not FAILED with an unbound-variable error."""
    _, session = await _create_contest_and_session(
        engine_db_factory, "already-ended", seconds=-1.0
    )

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    completed = await _get_session(engine_db_factory, session.id)
    assert completed.status == "COMPLETED"
    assert not (completed.session_metadata or {}).get("error")


@pytest.mark.asyncio
async def test_run_session_creates_observations(engine_db_factory):
    _, session = await _create_contest_and_session(engine_db_factory, "observations")

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)

    assert observations
    assert observations[0].session_id == session.id
    assert observations[0].sensors == {"mock_sensor": 5.0}


@pytest.mark.asyncio
async def test_run_session_observations_have_non_null_labels(engine_db_factory):
    _, session = await _create_contest_and_session(engine_db_factory, "labels")

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)

    assert observations
    assert all(observation.labels is not None for observation in observations)


@pytest.mark.asyncio
async def test_fault_schedule_produces_anomaly_labels(engine_db_factory):
    _, session = await _create_contest_and_session(
        engine_db_factory, "fault-labels", fault_schedule=MOCK_FAULT_SCHEDULE
    )

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)

    assert observations[0].labels["is_anomaly"] is True
    assert "mock_fault" in observations[0].labels["fault_ids"]


@pytest.mark.asyncio
async def test_concurrent_sessions_use_independent_twin_state(engine_db_factory):
    _, faulted_session = await _create_contest_and_session(
        engine_db_factory,
        "concurrent-faulted",
        fault_schedule=MOCK_FAULT_SCHEDULE,
        seconds=0.5,
    )
    _, normal_session = await _create_contest_and_session(
        engine_db_factory,
        "concurrent-normal",
        seconds=0.5,
    )

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await asyncio.gather(
            SimulationEngine().run_session(str(faulted_session.id), engine_db_factory),
            SimulationEngine().run_session(str(normal_session.id), engine_db_factory),
        )

    faulted_observations = await _get_observations(engine_db_factory, faulted_session.id)
    normal_observations = await _get_observations(engine_db_factory, normal_session.id)

    assert faulted_observations
    assert normal_observations
    assert all(
        observation.labels["is_anomaly"] is True
        for observation in faulted_observations
    )
    assert all(
        observation.labels["is_anomaly"] is False
        for observation in normal_observations
    )


@pytest.mark.asyncio
async def test_run_session_missing_twin_sets_failed(engine_db_factory):
    _, session = await _create_contest_and_session(
        engine_db_factory, "missing-twin", twin_id="missing_twin"
    )

    with registry_context():
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    failed = await _get_session(engine_db_factory, session.id)
    assert failed.status == "FAILED"
    assert failed.session_metadata["error"]


@pytest.mark.asyncio
async def test_run_session_missing_sensor_sets_failed(engine_db_factory):
    _, session = await _create_contest_and_session(
        engine_db_factory,
        "missing-sensor",
        sensor_configs=[{"sensor_id": "missing_sensor"}],
    )

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    failed = await _get_session(engine_db_factory, session.id)
    assert failed.status == "FAILED"


@pytest.mark.asyncio
async def test_run_session_sets_failed_when_twin_step_raises(engine_db_factory):
    _, session = await _create_contest_and_session(
        engine_db_factory, "failed", twin_id="failing_twin"
    )

    with registry_context(
        twins=[FailingTwin(twin_id="failing_twin")], sensors=[MockSensor()]
    ):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    failed = await _get_session(engine_db_factory, session.id)
    assert failed.status == "FAILED"
    assert "error" in failed.session_metadata


@pytest.mark.asyncio
async def test_run_session_applies_sensor_config_overrides(engine_db_factory):
    _, session = await _create_contest_and_session(
        engine_db_factory,
        "sensor-overrides",
        sensor_configs=[{"sensor_id": "mock_sensor", "noise_std": 10.0}],
        seed=42,
    )

    with registry_context(
        twins=[MockTwin(twin_id="mock_twin")],
        sensors=[ConfigurableNoisyMockSensor()],
    ):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)
    values = [observation.sensors["mock_sensor"] for observation in observations]

    assert len(values) > 1
    assert len(set(values)) > 1


@pytest.mark.asyncio
async def test_run_session_seed_reproduces_noisy_sensor_values(engine_db_factory):
    first_twin = MockTwin(twin_id="first_seed_twin")
    second_twin = MockTwin(twin_id="second_seed_twin")

    with registry_context(twins=[first_twin, second_twin], sensors=[NoisyMockSensor()]):
        _, first_session = await _create_contest_and_session(
            engine_db_factory, "first-seed", twin_id="first_seed_twin", seed=42
        )
        await SimulationEngine().run_session(str(first_session.id), engine_db_factory)

        _, second_session = await _create_contest_and_session(
            engine_db_factory, "second-seed", twin_id="second_seed_twin", seed=42
        )
        await SimulationEngine().run_session(str(second_session.id), engine_db_factory)

    first_observation = (await _get_observations(engine_db_factory, first_session.id))[0]
    second_observation = (
        await _get_observations(engine_db_factory, second_session.id)
    )[0]

    assert (
        first_observation.sensors["mock_sensor"]
        == second_observation.sensors["mock_sensor"]
    )


# ── Two-phase gating ──────────────────────────────────────────────────────────

class RecordingBroadcaster:
    """Captures every broadcast payload for assertions."""

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def broadcast(self, contest_id: str, payload: dict) -> None:
        self.payloads.append(payload)


async def _create_two_phase_contest_and_session(
    db_factory,
    name: str,
    observation_seconds: float = 0.4,
    horizon_seconds: float = 0.3,
    sampling_rate_hz: float = 20.0,
):
    now = datetime.now(timezone.utc)
    async with db_factory() as db:
        contest = Contest(
            name=name,
            status="ACTIVE",
            twin_id="mock_twin",
            sensor_configs=[{"sensor_id": "mock_sensor"}],
            fault_schedule=[],
            sampling_rate_hz=sampling_rate_hz,
            start_date=now,
            end_of_observation=now + timedelta(seconds=observation_seconds),
            prediction_horizon_seconds=horizon_seconds,
            end_date=now + timedelta(seconds=observation_seconds + horizon_seconds + 30),
        )
        db.add(contest)
        await db.commit()
        await db.refresh(contest)

        session = SimulationSession(
            contest_id=contest.id,
            twin_id="mock_twin",
            sampling_rate_hz=sampling_rate_hz,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return contest, session


@pytest.mark.asyncio
async def test_two_phase_stores_only_evaluation_observations(engine_db_factory):
    """The anti-cheat core: nothing is persisted during the observation phase;
    every evaluation-phase observation is persisted with clean ground truth."""
    _, session = await _create_two_phase_contest_and_session(
        engine_db_factory, "two-phase-storage"
    )
    broadcaster = RecordingBroadcaster()

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine(broadcaster=broadcaster).run_session(
            str(session.id), engine_db_factory
        )

    completed = await _get_session(engine_db_factory, session.id)
    assert completed.status == "COMPLETED"

    observations = await _get_observations(engine_db_factory, session.id)
    assert observations, "evaluation phase must persist observations"

    # Sensor messages broadcast during the observation phase carry sequence_ids;
    # no stored observation may share one (storage starts strictly after).
    streamed_ids = {
        p["sequence_id"] for p in broadcaster.payloads if "sensors" in p and "event" not in p
    }
    stored_ids = {obs.sequence_id for obs in observations}
    assert streamed_ids, "observation phase must broadcast sensor readings"
    assert streamed_ids.isdisjoint(stored_ids), (
        "broadcast (observation-phase) and stored (evaluation-phase) "
        "sequence_ids must not overlap"
    )

    # Every stored observation carries the clean latent value for scoring.
    for obs in observations:
        assert obs.ground_truth is not None
        assert "mock_sensor" in obs.ground_truth
        assert obs.labels is not None


@pytest.mark.asyncio
async def test_two_phase_broadcast_stops_at_evaluation_started(engine_db_factory):
    """Participants must never receive evaluation-phase sensor data."""
    contest, session = await _create_two_phase_contest_and_session(
        engine_db_factory, "two-phase-broadcast"
    )
    broadcaster = RecordingBroadcaster()

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine(broadcaster=broadcaster).run_session(
            str(session.id), engine_db_factory
        )

    events = [p for p in broadcaster.payloads if p.get("event") == "evaluation_started"]
    assert len(events) == 1, "exactly one evaluation_started event"

    expected_steps = round(
        contest.prediction_horizon_seconds * session.sampling_rate_hz
    )
    assert events[0]["evaluation_steps"] == expected_steps

    # No sensor payload may follow the phase-change event.
    event_index = broadcaster.payloads.index(events[0])
    after_event = broadcaster.payloads[event_index + 1:]
    assert all("sensors" not in p for p in after_event), (
        "no sensor readings may be broadcast after evaluation_started"
    )


# ── Engine notifications ──────────────────────────────────────────────────────

async def _create_user(db_factory, username: str, email: str, role: str):
    from epic_core.kernel.db.models import User

    async with db_factory() as db:
        user = User(
            username=username,
            email=email,
            password_hash="x",
            role=role,
            status="ACTIVE",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.mark.asyncio
async def test_session_failure_notifies_owner_and_admins(engine_db_factory):
    """A crashing twin must alert the contest owner and every administrator."""
    from epic_core.kernel.notifications import CollectingNotificationService, SessionFailed

    admin = await _create_user(
        engine_db_factory, "admin", "admin@example.com", "ADMINISTRATOR"
    )
    owner = await _create_user(
        engine_db_factory, "organizer", "organizer@example.com", "ORGANIZER"
    )
    contest, session = await _create_contest_and_session(
        engine_db_factory, "failure-notify"
    )
    async with engine_db_factory() as db:
        result = await db.execute(select(Contest).where(Contest.id == contest.id))
        db_contest = result.scalar_one()
        db_contest.created_by = owner.id
        await db.commit()

    collecting = CollectingNotificationService()
    with registry_context(
        twins=[FailingTwin(twin_id="mock_twin")], sensors=[MockSensor()]
    ):
        await SimulationEngine(notification_service=collecting).run_session(
            str(session.id), engine_db_factory
        )

    failed = await _get_session(engine_db_factory, session.id)
    assert failed.status == "FAILED"

    events = collecting.of_type(SessionFailed)
    recipients = {event.to_email for event in events}
    assert recipients == {"organizer@example.com", "admin@example.com"}
    assert all(event.contest_name == "failure-notify" for event in events)
    assert all(event.error for event in events)


@pytest.mark.asyncio
async def test_two_phase_completion_notifies_registered_participants(
    engine_db_factory,
):
    """When the evaluation window ends, registered participants must be told
    the submission window is open. Unregistered users must not be."""
    from epic_core.kernel.db.models import ContestRegistration
    from epic_core.kernel.notifications import (
        CollectingNotificationService,
        SubmissionWindowOpen,
    )

    registered = await _create_user(
        engine_db_factory, "student1", "student1@example.com", "PARTICIPANT"
    )
    await _create_user(
        engine_db_factory, "student2", "student2@example.com", "PARTICIPANT"
    )
    contest, session = await _create_two_phase_contest_and_session(
        engine_db_factory,
        "window-open-notify",
        observation_seconds=0.2,
        horizon_seconds=0.2,
    )
    async with engine_db_factory() as db:
        db.add(ContestRegistration(
            contest_id=contest.id,
            user_id=registered.id,
            status="REGISTERED",
        ))
        await db.commit()

    collecting = CollectingNotificationService()
    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine(notification_service=collecting).run_session(
            str(session.id), engine_db_factory
        )

    events = collecting.of_type(SubmissionWindowOpen)
    assert {event.to_email for event in events} == {"student1@example.com"}
    assert events[0].contest_name == "window-open-notify"
