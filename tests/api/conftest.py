import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from epic_api.dependencies import get_notification_service
from epic_api.main import create_app
from epic_core.config import Settings
from epic_core.db.base import create_all_tables
from epic_core.db.models import User
import epic_core.db.session as db_session_module
from epic_core.db.session import get_engine
from epic_core.db.session import get_session_factory
from epic_core.notifications import CollectingNotificationService
from epic_core.testing import test_registry_context


def _reset_db_state():
    db_session_module._engine = None
    db_session_module.AsyncSessionFactory = None


@pytest.fixture
def collecting_notifications():
    """A CollectingNotificationService shared across the test and the app."""
    return CollectingNotificationService()


@pytest.fixture
def client(collecting_notifications, tmp_path):
    _reset_db_state()
    # A per-test FILE database, not :memory:. An in-memory SQLite forces
    # SQLAlchemy onto a single shared connection (StaticPool), where every
    # session.close() rollback can wipe another session's flushed-but-
    # uncommitted work — the engine's background tasks then corrupt API
    # handlers mid-test. A file database gives each pooled connection real
    # transaction isolation, like production.
    database_url = f"sqlite+aiosqlite:///{tmp_path}/epic_test.db"
    settings = Settings(
        database_url=database_url,
        secret_key="test-secret-key-32-characters-xx",
        debug=False,
        admin_username="admin1",
        admin_email="admin@example.com",
        admin_password="admin-password",
        base_url="http://testserver",
    )

    with test_registry_context():
        db_session_module.init_db(database_url)

        async def _setup_tables():
            await create_all_tables(get_engine())

        asyncio.run(_setup_tables())
        app = create_app(settings=settings)
        app.dependency_overrides[get_notification_service] = lambda: collecting_notifications
        with TestClient(app) as test_client:
            yield test_client
        if db_session_module._engine is not None:
            asyncio.run(db_session_module._engine.dispose())
        _reset_db_state()


@pytest.fixture
def registered_user(client, admin_headers):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "student1",
            "email": "student@example.com",
            "password": "correct-password",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def auth_headers(client, registered_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": registered_user["username"], "password": "correct-password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def registered_admin(client):
    return {
        "username": "admin1",
        "email": "admin@example.com",
        "role": "ADMINISTRATOR",
        "id": None,
    }


@pytest.fixture
def admin_headers(client, registered_admin):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": registered_admin["username"],
            "password": "admin-password",
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def registered_organizer(client, admin_headers):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "organizer1",
            "email": "organizer@example.com",
            "password": "organizer-password",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201

    async def promote_organizer():
        async with get_session_factory()() as db:
            result = await db.execute(select(User).where(User.username == "organizer1"))
            user = result.scalar_one()
            user.role = "ORGANIZER"
            await db.commit()
            await db.refresh(user)
            return user

    asyncio.run(promote_organizer())
    user = response.json()
    user["role"] = "ORGANIZER"
    return user


@pytest.fixture
def organizer_headers(client, registered_organizer):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": registered_organizer["username"],
            "password": "organizer-password",
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def registered_contest(client, organizer_headers):
    """Create a minimal contest owned by the organizer fixture."""
    response = client.post(
        "/api/v1/contests",
        json={
            "name": "Test Contest",
            "twin_id": "mass_spring_damper",
            "sensor_configs": [{"sensor_id": "position"}],
            "sampling_rate_hz": 10.0,
            "start_date": "2030-01-01T00:00:00Z",
            "end_date": "2030-06-01T00:00:00Z",
            "end_of_observation": "2030-05-01T00:00:00Z",
            "prediction_horizon_seconds": 3600.0,
        },
        headers=organizer_headers,
    )
    assert response.status_code == 201, response.json()
    return response.json()


@pytest.fixture
def db_factory(client):
    return get_session_factory()
