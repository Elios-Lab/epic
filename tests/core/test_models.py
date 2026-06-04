import importlib
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from epic_core.db.base import create_all_tables, create_engine
from epic_core.db.models import Contest, SensorObservation, SimulationSession, User
import epic_core.db.session as db_session_module


@pytest_asyncio.fixture(scope="session")
async def async_session_factory():
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_all_tables(engine)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_session_factory):
    async with async_session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_get_db_before_init_db_raises_runtime_error():
    module = importlib.reload(db_session_module)

    with pytest.raises(RuntimeError, match="Database not initialised"):
        async for _ in module.get_db():
            pass


def _user(username: str = "alice", email: str = "alice@example.com") -> User:
    return User(
        username=username,
        email=email,
        password_hash="hashed-password",
    )


def _contest(name: str = "Contest") -> Contest:
    return Contest(
        name=name,
        twin_id="mechanical_system",
        scenario_id="normal_operation",
        sampling_rate_hz=10.0,
    )


async def _create_contest(db_session, name: str = "Contest") -> Contest:
    contest = _contest(name=name)
    db_session.add(contest)
    await db_session.commit()
    await db_session.refresh(contest)
    return contest


async def _create_user(db_session, username: str = "alice") -> User:
    user = _user(username=username, email=f"{username}@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_simulation_session(
    db_session, contest: Contest
) -> SimulationSession:
    session = SimulationSession(
        contest_id=contest.id,
        twin_id=contest.twin_id,
        scenario_id=contest.scenario_id,
        sampling_rate_hz=contest.sampling_rate_hz,
        session_metadata={"source": "test"},
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.mark.asyncio
async def test_create_user_and_query_by_username(db_session):
    user = await _create_user(db_session, username="user_query")

    result = await db_session.execute(
        select(User).where(User.username == "user_query")
    )
    queried_user = result.scalar_one()

    assert queried_user.id == user.id
    assert queried_user.email == "user_query@example.com"


@pytest.mark.asyncio
async def test_username_uniqueness_constraint_raises_integrity_error(db_session):
    db_session.add(_user(username="duplicate_username", email="first@example.com"))
    await db_session.commit()

    db_session.add(_user(username="duplicate_username", email="second@example.com"))

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_email_uniqueness_constraint_raises_integrity_error(db_session):
    db_session.add(_user(username="first_email_user", email="duplicate@example.com"))
    await db_session.commit()

    db_session.add(_user(username="second_email_user", email="duplicate@example.com"))

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_create_contest_and_query_by_name(db_session):
    contest = await _create_contest(db_session, name="Model Contest")

    result = await db_session.execute(
        select(Contest).where(Contest.name == "Model Contest")
    )
    queried_contest = result.scalar_one()

    assert queried_contest.id == contest.id
    assert queried_contest.twin_id == "mechanical_system"


@pytest.mark.asyncio
async def test_contest_default_status_is_draft(db_session):
    contest = await _create_contest(db_session, name="Draft Contest")

    assert contest.status == "DRAFT"


@pytest.mark.asyncio
async def test_create_simulation_session_and_query_it_back(db_session):
    contest = await _create_contest(db_session, name="Session Contest")
    simulation_session = await _create_simulation_session(db_session, contest)

    result = await db_session.execute(
        select(SimulationSession).where(SimulationSession.id == simulation_session.id)
    )
    queried_session = result.scalar_one()

    assert queried_session.contest_id == contest.id
    assert queried_session.twin_id == "mechanical_system"


@pytest.mark.asyncio
async def test_simulation_session_default_status_is_created(db_session):
    contest = await _create_contest(db_session, name="Status Contest")
    simulation_session = await _create_simulation_session(db_session, contest)

    assert simulation_session.status == "CREATED"


@pytest.mark.asyncio
async def test_simulation_session_metadata_stores_dict(db_session):
    contest = await _create_contest(db_session, name="Metadata Contest")
    simulation_session = await _create_simulation_session(db_session, contest)

    assert simulation_session.session_metadata == {"source": "test"}


@pytest.mark.asyncio
async def test_create_sensor_observation_and_query_it_back(db_session):
    contest = await _create_contest(db_session, name="Observation Contest")
    simulation_session = await _create_simulation_session(db_session, contest)
    observation = SensorObservation(
        session_id=simulation_session.id,
        sequence_id=1,
        timestamp=datetime.now(timezone.utc),
        sensors={"position": 0.1, "velocity": 1.2},
        labels=None,
    )
    db_session.add(observation)
    await db_session.commit()
    await db_session.refresh(observation)

    result = await db_session.execute(
        select(SensorObservation).where(SensorObservation.id == observation.id)
    )
    queried_observation = result.scalar_one()

    assert queried_observation.session_id == simulation_session.id


@pytest.mark.asyncio
async def test_sensor_observation_sensors_store_dict(db_session):
    contest = await _create_contest(db_session, name="Sensors Contest")
    simulation_session = await _create_simulation_session(db_session, contest)
    observation = SensorObservation(
        session_id=simulation_session.id,
        sequence_id=2,
        timestamp=datetime.now(timezone.utc),
        sensors={"position": 0.1, "velocity": 1.2},
    )
    db_session.add(observation)
    await db_session.commit()
    await db_session.refresh(observation)

    assert observation.sensors == {"position": 0.1, "velocity": 1.2}


@pytest.mark.asyncio
async def test_sensor_observation_labels_are_nullable(db_session):
    contest = await _create_contest(db_session, name="Labels Contest")
    simulation_session = await _create_simulation_session(db_session, contest)
    observation = SensorObservation(
        session_id=simulation_session.id,
        sequence_id=3,
        timestamp=datetime.now(timezone.utc),
        sensors={"position": 0.1, "velocity": 1.2},
        labels=None,
    )
    db_session.add(observation)
    await db_session.commit()
    await db_session.refresh(observation)

    assert observation.labels is None
