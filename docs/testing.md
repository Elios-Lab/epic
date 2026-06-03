# Testing Strategy

> Related: [Plugin System](plugin-system.md) · [Simulation Engine](simulation-engine.md) · [Error Handling](error-handling.md)

This document defines the testing strategy for the EPIC platform and its plugins.

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
│   └── mechanical/
│       ├── test_twin.py
│       ├── test_sensors.py
│       └── test_faults.py
└── conftest.py
```

---

# Testing Layers

## Unit Tests

Test individual classes in isolation.

Examples:
- Test a sensor's measurement pipeline with a known state
- Test a fault's `apply()` against a known state and dt
- Test a scenario's `get_fault_schedule()` output

Unit tests must not touch the database, the API, or the simulation engine.

## Integration Tests

Test interactions between components using a real (in-memory) database.

Examples:
- Test that a session created via the API can be run by the engine
- Test that a submission triggers correct scoring and leaderboard update

Integration tests use SQLite (`sqlite+aiosqlite:///:memory:`) to avoid external dependencies.

## Contract Tests

Verify that a plugin correctly implements an interface.

The EPIC Core provides a reusable contract test suite for each plugin type. Plugin authors run the contract tests against their implementation to confirm correctness before integration.

---

# Test Utilities Provided by the Core

The Core provides test utilities in `epic_core/testing.py`.

## MockTwin

A minimal in-memory digital twin for use in engine and registry tests:

```python
from epic_core.testing import MockTwin, MockScenario, MockSensor, MockFault

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

## MockScenario

```python
scenario = MockScenario(
    scenario_id="normal",
    fault_schedule=[
        {"fault_id": "mock_fault", "start_time": 10.0, "end_time": None, "severity": 1.0}
    ]
)
```

## TestRegistry

A pre-populated registry for test environments:

```python
from epic_core.testing import test_registry_context

with test_registry_context(twins=[MockTwin()], faults=[MockFault()]) as registries:
    # registries.twin, registries.sensor, registries.fault, registries.metric
    pass
```

`test_registry_context` is a context manager that installs a fresh registry for the duration of the test and restores the original on exit.

---

# Plugin Contract Tests

The Core provides a base contract test class for each plugin type.

Plugin authors inherit from the relevant base class and provide their implementation. The contract tests run automatically.

## DigitalTwinContractTests

```python
from epic_core.testing.contracts import DigitalTwinContractTests
from epic_twins.mechanical import MechanicalTwin

class TestMechanicalTwin(DigitalTwinContractTests):
    plugin = MechanicalTwin()
```

Contract tests verify:

- `twin_id` is a non-empty string
- `name` is a non-empty string
- `metadata()` contains required keys with correct types
- `create_initial_state()` returns a `SimulationState`
- `create_initial_state(initial_conditions={...})` applies overrides
- `step(state, dt)` returns a new `SimulationState`, does not modify `state`
- `step()` is called 100 times without raising exceptions
- `get_sensors()` returns a non-empty list of `Sensor` instances
- `get_faults()` returns a list of `Fault` instances
- `get_scenarios()` returns a non-empty list of `Scenario` instances

## SensorContractTests

```python
from epic_core.testing.contracts import SensorContractTests
from epic_twins.mechanical.sensors import PositionSensor

class TestPositionSensor(SensorContractTests):
    plugin = PositionSensor()
    sample_state = MechanicalState(position=0.5, velocity=1.0,
                                   acceleration=0.0, temperature=25.0)
```

Contract tests verify:

- `sensor_id`, `name`, `unit` are non-empty strings
- `metadata()` contains required keys
- `observe(sample_state)` returns a `float`
- `observe()` is called 1000 times without raising exceptions

## FaultContractTests

```python
from epic_core.testing.contracts import FaultContractTests
from epic_twins.mechanical.faults import IncreasedDampingFault

class TestIncreasedDampingFault(FaultContractTests):
    plugin = IncreasedDampingFault()
    sample_state = MechanicalState(position=0.5, velocity=1.0,
                                   acceleration=0.0, temperature=25.0)
```

Contract tests verify:

- `fault_id` and `name` are non-empty strings
- `metadata()` contains required keys
- `current_severity` is `0.0` before activation
- `activate(0.5)` sets `current_severity` to `0.5`
- `deactivate()` resets `current_severity` to `0.0`
- `apply(state, dt)` does not raise exceptions
- `apply()` does not replace the state object (modifies in place)
- For `SensorFault`: `apply_to_measurement(1.0)` returns a `float`
- For `SensorFault`: `target_sensor_ids` is a list

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
uv run pytest tests/twins/mechanical/test_twin.py -v
```

---

# CI Requirements

The CI pipeline must run:

- All unit tests
- All contract tests for every registered plugin
- All API integration tests
- Coverage must not drop below 80% for `epic_core`

Tests must pass before any pull request can be merged.

---

# What Not to Test

Do not write tests that assert specific floating-point values from simulation physics. These are brittle and will break with any tuning change.

Instead, assert structural properties: the observation has the expected sensor keys, the state fields are within plausible ranges, faults increase/decrease the relevant quantity in the expected direction.
