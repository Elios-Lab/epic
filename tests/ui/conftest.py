"""
Shared fixtures for Playwright UI tests.

The test suite spins up a real EPIC server in-process (on a random port),
then drives a Chromium browser against it via Playwright.
"""

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import uvicorn
from playwright.sync_api import Page, sync_playwright

from epic_api.main import create_app
from epic_core.config import Settings
from epic_core.db.base import create_all_tables
from epic_core.db.session import get_engine, get_session_factory, init_db
import epic_core.db.session as db_session_module
from epic_core.testing import test_registry_context
from sqlalchemy import select
from epic_core.db.models import User


# ── Server fixture ────────────────────────────────────────────────────────────

class _ServerThread(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__(daemon=True)
        self.server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


@pytest.fixture(scope="session")
def live_server():
    """Start a real EPIC server on localhost:18999 for the whole test session."""
    db_session_module._engine = None
    db_session_module.AsyncSessionFactory = None

    database_url = "sqlite+aiosqlite:///./test_ui.db"
    settings = Settings(
        database_url=database_url,
        secret_key="ui-test-secret-key-32-characters",
        debug=False,
        admin_username="admin",
        admin_email="admin@test.com",
        admin_password="admin-password",
    )

    with test_registry_context():
        init_db(database_url)
        asyncio.run(create_all_tables(get_engine()))

        app = create_app(settings=settings)
        thread = _ServerThread(app, host="127.0.0.1", port=18999)
        thread.start()
        # Wait for the server to be ready.
        time.sleep(1.5)
        yield "http://127.0.0.1:18999"
        thread.stop()

    db_session_module._engine = None
    db_session_module.AsyncSessionFactory = None
    import os
    if os.path.exists("./test_ui.db"):
        os.remove("./test_ui.db")


@pytest.fixture(scope="session")
def organizer_token(live_server):
    """Create an organizer user and return a valid JWT token."""
    import requests

    # Create organizer via admin
    admin_login = requests.post(
        f"{live_server}/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )
    admin_token = admin_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    requests.post(
        f"{live_server}/api/v1/users",
        json={"username": "organizer_ui", "email": "org@test.com", "password": "org-pass"},
        headers=headers,
    )

    async def _promote():
        async with get_session_factory()() as db:
            result = await db.execute(select(User).where(User.username == "organizer_ui"))
            user = result.scalar_one()
            user.role = "ORGANIZER"
            await db.commit()

    # asyncio.run() can't be called when there's already a running event loop
    # (pytest-asyncio starts one for the session).  Run the promotion in a
    # fresh background thread that has its own loop.
    import threading
    exc_box: list = []
    def _run():
        try:
            asyncio.run(_promote())
        except Exception as e:
            exc_box.append(e)
    t = threading.Thread(target=_run)
    t.start()
    t.join()
    if exc_box:
        raise exc_box[0]

    login = requests.post(
        f"{live_server}/api/v1/auth/login",
        json={"username": "organizer_ui", "password": "org-pass"},
    )
    return login.json()["access_token"]


@pytest.fixture(scope="session")
def participant_token(live_server):
    """Create a participant user and return a valid JWT token."""
    import requests

    admin_login = requests.post(
        f"{live_server}/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )
    admin_token = admin_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    requests.post(
        f"{live_server}/api/v1/users",
        json={"username": "participant_ui", "email": "part@test.com", "password": "part-pass"},
        headers=headers,
    )

    login = requests.post(
        f"{live_server}/api/v1/auth/login",
        json={"username": "participant_ui", "password": "part-pass"},
    )
    return login.json()["access_token"]


# ── Browser / page fixtures ───────────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_context(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(base_url=live_server)
        yield context
        browser.close()


@pytest.fixture
def unauth_page(browser_context, live_server):
    """Open a fresh page with no token — shows the landing/login state."""
    pg = browser_context.new_page()
    pg.goto(live_server)
    pg.evaluate("() => localStorage.removeItem('epic_token')")
    pg.reload()
    pg.wait_for_load_state("networkidle")
    yield pg
    pg.close()


@pytest.fixture
def page(browser_context, live_server, organizer_token):
    """Open a fresh page, inject the organizer token, and navigate to the app."""
    pg = browser_context.new_page()
    pg.goto(live_server)
    # Inject the auth token so the app boots as the organizer without
    # going through the login form.
    pg.evaluate(f"() => localStorage.setItem('epic_token', '{organizer_token}')")
    pg.reload()
    pg.wait_for_load_state("networkidle")
    yield pg
    pg.close()


# ── Contest helpers ───────────────────────────────────────────────────────────

def create_active_contest(live_server: str, token: str) -> dict:
    """Create and activate a two-phase contest via the API."""
    import requests
    import uuid

    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(timezone.utc)
    contest_data = {
        "name": f"UI Monitor Test {uuid.uuid4().hex[:8]}",
        "description": "Created by UI test suite",
        "visibility": "PUBLIC",
        "twin_id": "mass_spring_damper",
        "sensor_configs": [{"sensor_id": "position", "noise_std": 0.001}],
        "fault_schedule": [],
        "initial_conditions": {"position": 0.1, "velocity": 0.0},
        "sampling_rate_hz": 10.0,
        "start_date": now.isoformat(),
        "end_of_observation": (now + timedelta(hours=1)).isoformat(),
        "prediction_horizon_seconds": 60,
        "end_date": (now + timedelta(hours=2)).isoformat(),
        "task_type": "FORECASTING",
        "metric_ids": ["mae"],
        "score_against": "ground_truth",
    }
    resp = requests.post(f"{live_server}/api/v1/contests", json=contest_data, headers=headers)
    assert resp.status_code == 201
    contest = resp.json()

    activate = requests.patch(
        f"{live_server}/api/v1/contests/{contest['contest_id']}",
        json={"status": "ACTIVE"},
        headers=headers,
    )
    assert activate.status_code == 200
    time.sleep(0.5)  # let the engine start
    return activate.json()


def close_contest(live_server: str, token: str, contest_id: str):
    """Close then delete the contest so its name can be reused and the DB stays clean."""
    import requests
    headers = {"Authorization": f"Bearer {token}"}
    # Must be CLOSED before it can be deleted.
    requests.patch(
        f"{live_server}/api/v1/contests/{contest_id}",
        json={"status": "CLOSED"},
        headers=headers,
    )
    requests.delete(
        f"{live_server}/api/v1/contests/{contest_id}",
        headers=headers,
    )
