from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from epic_core.db.base import create_all_tables, create_engine
from epic_core.db.models import Contest, SensorObservation, SimulationSession
from epic_core.engine import SimulationEngine
from epic_core.testing import (
    MockFault,
    MockScenario,
    MockSensor,
    MockTwin,
    test_registry_context as registry_context,
)


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


async def _create_contest_and_session(
    db_factory,
    name: str,
    twin_id: str = "mock_twin",
    scenario_id: str = "normal",
    seed: int | None = None,
    seconds: float = 1.0,
) -> tuple[Contest, SimulationSession]:
    async with db_factory() as db:
        contest = Contest(
            name=name,
            twin_id=twin_id,
            scenario_id=scenario_id,
            sampling_rate_hz=10.0,
            end_date=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        )
        db.add(contest)
        await db.commit()
        await db.refresh(contest)

        session = SimulationSession(
            contest_id=contest.id,
            twin_id=twin_id,
            scenario_id=scenario_id,
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

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    completed = await _get_session(engine_db_factory, session.id)
    assert completed.status == "COMPLETED"


@pytest.mark.asyncio
async def test_run_session_creates_observations(engine_db_factory):
    _, session = await _create_contest_and_session(engine_db_factory, "observations")

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)

    assert observations
    assert observations[0].session_id == session.id
    assert observations[0].sensors == {"mock_sensor": 5.0}


@pytest.mark.asyncio
async def test_run_session_observations_have_non_null_labels(engine_db_factory):
    _, session = await _create_contest_and_session(engine_db_factory, "labels")

    with registry_context(twins=[MockTwin(twin_id="mock_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)

    assert observations
    assert all(observation.labels is not None for observation in observations)


@pytest.mark.asyncio
async def test_fault_scenario_training_labels_mark_anomaly(engine_db_factory):
    _, session = await _create_contest_and_session(engine_db_factory, "fault-labels")
    fault = MockFault(fault_id="mock_fault")
    scenario = MockFaultScenario()
    twin = ConfigurableMockTwin(scenario=scenario, fault=fault)

    with registry_context(twins=[twin], faults=[fault]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)

    assert observations[0].labels["is_anomaly"] is True
    assert observations[0].labels["fault_ids"]


@pytest.mark.asyncio
async def test_fault_scenario_applies_mock_fault(engine_db_factory):
    _, session = await _create_contest_and_session(engine_db_factory, "fault-apply")
    fault = MockFault(fault_id="mock_fault")
    scenario = MockFaultScenario()
    twin = ConfigurableMockTwin(scenario=scenario, fault=fault)

    with registry_context(twins=[twin], faults=[fault]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    assert fault.apply_count > 0


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
async def test_run_session_missing_scenario_sets_failed(engine_db_factory):
    _, session = await _create_contest_and_session(
        engine_db_factory, "missing-scenario", scenario_id="missing"
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

    with registry_context(twins=[FailingTwin(twin_id="failing_twin")]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    failed = await _get_session(engine_db_factory, session.id)
    assert failed.status == "FAILED"
    assert "error" in failed.session_metadata


@pytest.mark.asyncio
async def test_run_session_seed_reproduces_noisy_sensor_values(engine_db_factory):
    first_twin = ConfigurableMockTwin(
        twin_id="first_seed_twin", sensor=NoisyMockSensor()
    )
    second_twin = ConfigurableMockTwin(
        twin_id="second_seed_twin", sensor=NoisyMockSensor()
    )

    with registry_context(twins=[first_twin, second_twin]):
        _, first_session = await _create_contest_and_session(
            engine_db_factory, "first-seed", twin_id="first_seed_twin", seed=42
        )
        await SimulationEngine().run_session(str(first_session.id), engine_db_factory)

        _, second_session = await _create_contest_and_session(
            engine_db_factory, "second-seed", twin_id="second_seed_twin", seed=42
        )
        await SimulationEngine().run_session(str(second_session.id), engine_db_factory)

    first_observation = (await _get_observations(engine_db_factory, first_session.id))[0]
    second_observation = (await _get_observations(engine_db_factory, second_session.id))[0]

    assert (
        first_observation.sensors["mock_sensor"]
        == second_observation.sensors["mock_sensor"]
    )
