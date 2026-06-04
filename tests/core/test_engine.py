from datetime import datetime, timezone

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from epic_core.db.base import create_all_tables, create_engine
from epic_core.db.models import SensorObservation, SimulationSession, User
from epic_core.engine import SimulationEngine
from epic_core.testing import MockFault, MockScenario, MockSensor, MockTwin, test_registry_context as registry_context


class FailingTwin(MockTwin):
    def step(self, state, dt):
        raise RuntimeError("step failed")


class MockFaultScenario(MockScenario):
    def get_fault_schedule(self) -> list[dict]:
        return [
            {
                "fault_id": "mock_fault",
                "start_time": 0.0,
                "end_time": None,
                "severity": 0.5,
            }
        ]


class ConfigurableMockTwin(MockTwin):
    def __init__(
        self,
        twin_id: str = "mock_twin",
        scenario=None,
        fault=None,
        sensor=None,
    ) -> None:
        super().__init__(twin_id=twin_id)
        self._scenario = scenario or self._scenario
        self._fault = fault or self._fault
        self._sensor = sensor or self._sensor


class NoisyMockSensor(MockSensor):
    def __init__(self, sensor_id: str = "mock_sensor", noise_std: float = 1.0) -> None:
        super().__init__(sensor_id=sensor_id, constant_value=5.0)
        self.noise_std = noise_std

    def observe(self, state) -> float:
        return float(self._constant_value + np.random.normal(0.0, self.noise_std))


@pytest_asyncio.fixture
async def engine_db_factory():
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_all_tables(engine)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _create_user(db_factory, username: str = "engine_user") -> User:
    async with db_factory() as db:
        user = User(
            username=username,
            email=f"{username}@example.com",
            password_hash="hashed-password",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _create_session(
    db_factory,
    user: User,
    mode: str = "TRAINING",
    twin_id: str = "mock_twin",
    scenario_id: str = "normal",
    seed: int | None = None,
) -> SimulationSession:
    async with db_factory() as db:
        session = SimulationSession(
            user_id=user.id,
            twin_id=twin_id,
            scenario_id=scenario_id,
            mode=mode,
            sampling_rate_hz=10.0,
            duration_seconds=1.0,
            seed=seed,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session


async def _get_session(db_factory, session_id):
    async with db_factory() as db:
        result = await db.execute(
            select(SimulationSession).where(SimulationSession.id == session_id)
        )
        return result.scalar_one()


@pytest.mark.asyncio
async def test_run_session_completes_and_sets_status(engine_db_factory):
    user = await _create_user(engine_db_factory, "complete_user")
    session = await _create_session(engine_db_factory, user)

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    completed = await _get_session(engine_db_factory, session.id)
    assert completed.status == "COMPLETED"


@pytest.mark.asyncio
async def test_run_session_creates_observations(engine_db_factory):
    user = await _create_user(engine_db_factory, "observation_user")
    session = await _create_session(engine_db_factory, user)

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    async with engine_db_factory() as db:
        result = await db.execute(select(SensorObservation))
        observation = result.scalars().first()

    assert observation.session_id == session.id
    assert observation.sensors == {"mock_sensor": 5.0}


@pytest.mark.asyncio
async def test_observation_count_matches_expected_steps(engine_db_factory):
    user = await _create_user(engine_db_factory, "count_user")
    session = await _create_session(engine_db_factory, user)

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    async with engine_db_factory() as db:
        count = (
            await db.execute(
                select(func.count()).select_from(SensorObservation).where(
                    SensorObservation.session_id == session.id
                )
            )
        ).scalar_one()

    assert count == 10


@pytest.mark.asyncio
async def test_training_session_observations_include_labels(engine_db_factory):
    user = await _create_user(engine_db_factory, "training_user")
    session = await _create_session(engine_db_factory, user, mode="TRAINING")

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    async with engine_db_factory() as db:
        observation = (await db.execute(select(SensorObservation))).scalars().first()

    assert observation.labels is not None
    assert observation.labels["is_anomaly"] is False


@pytest.mark.asyncio
async def test_validation_session_observations_have_no_labels(engine_db_factory):
    user = await _create_user(engine_db_factory, "validation_user")
    session = await _create_session(engine_db_factory, user, mode="VALIDATION")

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    async with engine_db_factory() as db:
        observation = (await db.execute(select(SensorObservation))).scalars().first()

    assert observation.labels is None


@pytest.mark.asyncio
async def test_run_session_sets_failed_when_twin_step_raises(engine_db_factory):
    user = await _create_user(engine_db_factory, "failed_user")
    session = await _create_session(engine_db_factory, user, twin_id="failing_twin")

    with registry_context(twins=[FailingTwin(twin_id="failing_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    failed = await _get_session(engine_db_factory, session.id)
    assert failed.status == "FAILED"
    assert "error" in failed.session_metadata


@pytest.mark.asyncio
async def test_fault_scenario_training_labels_mark_anomaly(engine_db_factory):
    user = await _create_user(engine_db_factory, "fault_labels_user")
    session = await _create_session(engine_db_factory, user, mode="TRAINING")
    fault = MockFault(fault_id="mock_fault")
    scenario = MockFaultScenario()
    twin = ConfigurableMockTwin(scenario=scenario, fault=fault)

    with registry_context(twins=[twin], faults=[fault]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    async with engine_db_factory() as db:
        observation = (await db.execute(select(SensorObservation))).scalars().first()

    assert observation.labels["is_anomaly"] is True
    assert observation.labels["fault_ids"]


@pytest.mark.asyncio
async def test_fault_scenario_applies_mock_fault(engine_db_factory):
    user = await _create_user(engine_db_factory, "fault_apply_user")
    session = await _create_session(engine_db_factory, user, mode="TRAINING")
    fault = MockFault(fault_id="mock_fault")
    scenario = MockFaultScenario()
    twin = ConfigurableMockTwin(scenario=scenario, fault=fault)

    with registry_context(twins=[twin], faults=[fault]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    assert fault.apply_count > 0


@pytest.mark.asyncio
async def test_run_session_missing_twin_sets_failed(engine_db_factory):
    user = await _create_user(engine_db_factory, "missing_twin_user")
    session = await _create_session(engine_db_factory, user, twin_id="missing_twin")

    with registry_context():
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    failed = await _get_session(engine_db_factory, session.id)
    assert failed.status == "FAILED"
    assert failed.session_metadata["error"]


@pytest.mark.asyncio
async def test_run_session_missing_scenario_sets_failed(engine_db_factory):
    user = await _create_user(engine_db_factory, "missing_scenario_user")
    session = await _create_session(
        engine_db_factory, user, twin_id="mock_twin", scenario_id="missing"
    )

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    failed = await _get_session(engine_db_factory, session.id)
    assert failed.status == "FAILED"


@pytest.mark.asyncio
async def test_run_session_seed_reproduces_noisy_sensor_values(engine_db_factory):
    user = await _create_user(engine_db_factory, "seed_user")
    first_session = await _create_session(
        engine_db_factory, user, twin_id="first_seed_twin", seed=42
    )
    second_session = await _create_session(
        engine_db_factory, user, twin_id="second_seed_twin", seed=42
    )

    first_twin = ConfigurableMockTwin(
        twin_id="first_seed_twin", sensor=NoisyMockSensor()
    )
    second_twin = ConfigurableMockTwin(
        twin_id="second_seed_twin", sensor=NoisyMockSensor()
    )
    with registry_context(twins=[first_twin, second_twin]):
        await SimulationEngine().run_session(str(first_session.id), engine_db_factory)
        await SimulationEngine().run_session(str(second_session.id), engine_db_factory)

    async with engine_db_factory() as db:
        first_observation = (
            await db.execute(
                select(SensorObservation)
                .where(SensorObservation.session_id == first_session.id)
                .order_by(SensorObservation.sequence_id)
            )
        ).scalars().first()
        second_observation = (
            await db.execute(
                select(SensorObservation)
                .where(SensorObservation.session_id == second_session.id)
                .order_by(SensorObservation.sequence_id)
            )
        ).scalars().first()

    assert first_observation.sensors["mock_sensor"] == second_observation.sensors["mock_sensor"]
