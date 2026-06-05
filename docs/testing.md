# Testing Strategy

> Related: [Simulation Engine](simulation-engine.md) · [Digital Twins](digital-twins.md) · [Error Handling](error-handling.md)

This document defines the testing strategy for the EPIC platform.

---

# Test Structure

Tests live in the `tests/` directory, mirroring the source structure:

```text
tests/
├── core/
│   ├── test_registry.py
│   ├── test_simulation_engine.py
│   └── test_scoring.py
├── api/
│   ├── test_auth.py
│   ├── test_contests.py
│   ├── test_sessions.py
│   └── test_submissions.py
├── twins/
│   └── mass_spring_damper/
│       ├── test_twin.py
│       └── test_faults.py
├── sensors/
│   ├── test_position_sensor.py
│   ├── test_velocity_sensor.py
│   └── test_temperature_sensor.py
└── conftest.py
```

---

# Testing Layers

## Unit Tests

Test individual classes in isolation.

Examples:
- Test a sensor's measurement pipeline with a known state
- Test a fault's `apply()` against a known state and dt

Unit tests must not touch the database, the API, or the simulation engine.

## Integration Tests

Test interactions between components using a real (in-memory) database.

Examples:
- Test that a session created via the API can be run by the engine
- Test that a submission triggers correct scoring and leaderboard update

Integration tests use SQLite (`sqlite+aiosqlite:///:memory:`) to avoid external dependencies.

## Contract Tests

Verify that a twin or sensor correctly implements its interface.

The EPIC Core provides a reusable contract test suite for each interface type. Authors run the contract tests against their implementation to confirm correctness before integration.

---

# Test Utilities Provided by the Core

The Core provides test utilities in `epic_core/testing.py`.

## MockTwin

A minimal in-memory digital twin for use in engine and registry tests:

```python
from epic_core.testing import MockTwin, MockSensor, MockFault

twin = MockTwin(twin_id="mock_twin")
```

`MockTwin` implements the full `DigitalTwin` interface with a trivial oscillating state. Its sensors produce predictable values, making assertions straightforward.

## MockSensor

```python
sensor = MockSensor(sensor_id="mock_sensor", constant_value=5.0)
# sensor.observe(any_state) always returns 5.0
```

## MockFault

```python
fault = MockFault(fault_id="mock_fault")
# apply() is a no-op; records how many times it was called
assert fault.apply_count == 3
```

## TestRegistry

A pre-populated registry for test environments:

```python
from epic_core.testing import test_registry_context

with test_registry_context(twins=[MockTwin()], sensors=[MockSensor()]) as registries:
    # registries.twin, registries.sensor, registries.metric
    pass
```

`test_registry_context` is a context manager that installs a fresh registry for the duration of the test and restores the original on exit.

---

# Contract Tests

The Core provides a base contract test class for each interface type. Inherit from the relevant base class and provide your implementation.

## DigitalTwinContractTests

```python
from epic_core.testing.contracts import DigitalTwinContractTests
from epic_twins.mechanical.twin import MechanicalTwin

class TestMechanicalTwin(DigitalTwinContractTests):
    twin = MechanicalTwin()
```

Contract tests verify:

- `twin_id` and `name` are non-empty strings
- `metadata()` contains required keys
- `configure(None, [])` returns a `SimulationState`
- `configure(initial_conditions={...}, fault_schedule=[...])` applies overrides
- `step(state, dt)` returns a new `SimulationState`, does not modify `state` in place
- `step()` is called 100 times without raising exceptions
- `get_active_faults()` returns a list of dicts with `fault_id` and `severity` keys
- `supported_quantities()` returns a non-empty `set[PhysicalQuantity]`
- `get_faults()` returns a list of `FaultDescriptor` instances

## SensorContractTests

```python
from epic_core.testing.contracts import SensorContractTests
from epic_sensors.linear.position import PositionSensor
from epic_twins.mechanical.twin import MechanicalState

class TestPositionSensor(SensorContractTests):
    sensor = PositionSensor()
    sample_state = MechanicalState(position=0.5, velocity=1.0,
                                   acceleration=0.0, temperature=25.0,
                                   mass=1.0, stiffness=10.0, damping=0.5)
```

Contract tests verify:

- `sensor_id`, `name`, `unit` are non-empty strings
- `metadata()` contains required keys
- `observe(sample_state)` returns a `float`
- `observe()` is called 1000 times without raising exceptions

---

# API Testing

API tests use FastAPI's `TestClient` with a test database and a test registry.

```python
import pytest
from fastapi.testclient import TestClient
from epic_api.main import create_app
from epic_core.testing import test_registry_context, MockTwin

@pytest.fixture
def client():
    with test_registry_context(twins=[MockTwin()]):
        app = create_app(database_url="sqlite+aiosqlite:///:memory:")
        with TestClient(app) as c:
            yield c

def test_list_twins(client):
    response = client.get("/api/v1/twins")
    assert response.status_code == 200
    assert len(response.json()["twins"]) == 1
```

API tests must never use the production database URL or registry. Always use the test fixtures.

---

# Running Tests

```bash
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/core tests/twins

# API tests only
uv run pytest tests/api

# With coverage
uv run pytest --cov=epic_core --cov=epic_api --cov-report=term-missing

# A specific contract test suite
uv run pytest tests/twins/mass_spring_damper/test_twin.py -v
```

---

# CI Requirements

The CI pipeline must run:

- All unit tests
- All contract tests for every registered twin and sensor
- All API integration tests
- Coverage must not drop below 80% for `epic_core`

Tests must pass before any pull request can be merged.

---

# What Not to Test

Do not write tests that assert specific floating-point values from simulation physics. These are brittle and will break with any tuning change.

Instead, assert structural properties: the observation has the expected sensor keys, the state fields are within plausible ranges, faults increase/decrease the relevant quantity in the expected direction.
