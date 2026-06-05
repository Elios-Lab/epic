import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from epic_api.main import create_app
from epic_core.config import Settings
from epic_core.db.models import User
import epic_core.db.session as db_session_module
from epic_core.db.session import get_session_factory
from epic_core.testing import test_registry_context


def _reset_db_state():
    db_session_module._engine = None
    db_session_module.AsyncSessionFactory = None


@pytest.fixture
def client():
    _reset_db_state()
    database_url = "sqlite+aiosqlite:///:memory:"
    settings = Settings(
        database_url=database_url,
        secret_key="test-secret-key-32-characters-xx",
        debug=False,
        admin_username="admin1",
        admin_email="admin@example.com",
        admin_password="admin-password",
    )

    with test_registry_context():
        with TestClient(create_app(settings=settings)) as test_client:
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
def db_factory(client):
    return get_session_factory()
