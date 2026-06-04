import asyncio

import pytest
from fastapi.testclient import TestClient

from epic_api.main import create_app
from epic_core.config import Settings
from epic_core.db.base import create_all_tables
import epic_core.db.session as db_session_module
from epic_core.db.session import init_db
from epic_core.testing import test_registry_context
from epic_twins.mechanical.twin import MechanicalTwin


def _reset_db_state():
    db_session_module._engine = None
    db_session_module.AsyncSessionFactory = None


@pytest.fixture
def client():
    _reset_db_state()
    database_url = "sqlite+aiosqlite:///:memory:"
    init_db(database_url)
    assert db_session_module._engine is not None
    asyncio.run(create_all_tables(db_session_module._engine))
    settings = Settings(
        database_url=database_url,
        secret_key="test-secret-key-32-characters-xx",
        debug=False,
    )

    with test_registry_context(twins=[MechanicalTwin()]):
        test_client = TestClient(create_app(settings=settings))
        try:
            yield test_client
        finally:
            test_client.close()
            asyncio.run(db_session_module._engine.dispose())
            _reset_db_state()


@pytest.fixture
def registered_user(client):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "student1",
            "email": "student@example.com",
            "password": "correct-password",
        },
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
