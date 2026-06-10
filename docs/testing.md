# Testing Strategy

> Related: [Simulation Engine](simulation-engine.md) · [Digital Twins](digital-twins.md) · [Error Handling](error-handling.md)

This document defines the testing strategy for the EPIC platform: how the suite is organized, which utilities the Core provides, and what the conventions are for writing new tests.

---

# Test Structure

Tests live in the `tests/` directory, mirroring the source structure. `tests/core/` covers the registry, the engine, the broadcaster, configuration, interfaces, models, and scoring in isolation. `tests/api/` holds the integration suite — one module per router (auth, contests, registrations, submissions, leaderboard, invitations, organizer requests, sessions, templates, twins, users, websocket) plus end-to-end scenarios such as the full contest stream and restart recovery. `tests/twins/` contains one package per built-in twin with dedicated twin and fault tests, and `tests/sensors/` covers the sensor pipeline. A separate `tests/ui/` suite drives the web frontend with Playwright; it is excluded from the default pytest run (see `norecursedirs` in `pyproject.toml`) and must be invoked explicitly with `uv run pytest tests/ui`.

---

# Testing Layers

The suite is organized in two main layers. **Unit tests** exercise individual classes in isolation — a sensor's measurement pipeline against a known state, a fault's `apply()` against a known state and `dt`, the registry's validation rules. Unit tests must not touch the database, the API, or the simulation engine. **Integration tests** exercise interactions between components against a real, in-memory database: that a session created via the API can be run by the engine, that a submission triggers scoring and a leaderboard update, that a server restart recovers orphaned sessions. Integration tests use SQLite (`sqlite+aiosqlite:///:memory:`) so the suite has no external dependencies.

A third layer is planned but not yet implemented: **contract tests**, reusable interface-conformance suites that a twin or sensor author runs against their implementation (does `step()` return a new state without mutating the old one, does `metadata()` contain the required keys, does `observe()` survive a thousand calls). Today each built-in twin carries equivalent checks in its own test package; extracting them into a reusable `DigitalTwinContractTests` base class in `epic_core.testing` is the intended path, so that third-party plugin authors can validate their implementations before integration.

---

# Test Utilities Provided by the Core

The Core ships its test doubles in `epic_core/testing.py`, so that engine, registry, and API tests never need a real twin or sensor.

`MockTwin` is a minimal in-memory digital twin implementing the full `DigitalTwin` interface. It accepts a fault schedule via `configure()` and manages fault activation internally, exposing active faults through `get_active_faults()` — which makes it sufficient even for tests that exercise label generation.

```python
from epic_core.testing import MockTwin, MockSensor, MockFaultDescriptor

twin = MockTwin(twin_id="mock_twin")
sensor = MockSensor(sensor_id="mock_sensor", constant_value=5.0)  # observe() always returns 5.0
fault = MockFaultDescriptor(fault_id="mock_fault")                # lightweight descriptor
```

`test_registry_context` is a context manager that installs fresh registries for the duration of a test and restores the originals on exit, which keeps tests independent of whatever plugins the application registered at startup:

```python
from epic_core.testing import test_registry_context

with test_registry_context(twins=[MockTwin()], sensors=[MockSensor()]):
    ...
```

---

# API Testing

API tests use FastAPI's `TestClient` together with a test `Settings` object pointing at an in-memory database and a test registry context. The canonical fixture lives in `tests/api/conftest.py`; in simplified form:

```python
import pytest
from fastapi.testclient import TestClient
from epic_api.main import create_app
from epic_core.config import Settings
from epic_core.testing import test_registry_context

@pytest.fixture
def client():
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        secret_key="test-secret-key-32-characters-xx",
        admin_username="admin1",
        admin_email="admin@example.com",
        admin_password="admin-password",
    )
    with test_registry_context():
        app = create_app(settings=settings)
        with TestClient(app) as c:
            yield c
```

The real fixture additionally resets the database session factory between tests and injects a collecting notification service so email side effects can be asserted without sending anything. API tests must never use the production database URL or the production registries — always go through the fixtures.

---

# Running Tests

```bash
uv run pytest                          # all tests (UI suite excluded)
uv run pytest tests/core tests/twins   # unit tests only
uv run pytest tests/api                # API integration tests only
uv run pytest tests/ui                 # Playwright UI tests (requires playwright install)
uv run pytest --cov=epic_core --cov=epic_api --cov-report=term-missing
```

---

# CI Requirements

The CI pipeline runs the full unit and API integration suites on every pull request, and tests must pass before merging. Coverage for `epic_core` must not drop below 80%. When the contract-test layer lands, CI will additionally run the contract suite against every registered twin and sensor, turning interface conformance into a merge gate for new plugins.

---

# What Not to Test

Do not write tests that assert specific floating-point values from simulation physics. These are brittle and will break with any tuning change. Instead, assert structural properties: the observation has the expected sensor keys, the state fields are within plausible ranges, faults move the relevant quantity in the expected direction. A good fault test asserts that bearing wear *raises* vibration, not that vibration equals 3.7214.
