# Plugin Registry

> Related: [Plugin System](plugin-system.md) — interfaces · [Simulation Engine](simulation-engine.md) — consumer · [Digital Twins](digital-twins.md) · [Sensors](sensors.md) · [Faults](faults.md)

The Plugin Registry is the discovery and lookup mechanism for all EPIC plugins.

It is part of the EPIC Core and lives in `epic_core/registry.py`.

The API layer and the simulation engine never instantiate plugin classes directly. They always go through the registry.

---

# Registry Location

```text
epic_core/
└── registry.py     ← all registry classes live here
```

There is one registry per plugin category:

```python
from epic_core.registry import (
    twin_registry,
    sensor_registry,
    fault_registry,
    scenario_registry,
    metric_registry,
)
```

These are module-level singletons. They are initialised once at application startup and shared across all components.

Note: `scenario_registry` and `metric_registry` exist but are not used by the simulation engine in Phase 1. Scenarios are resolved through `twin.get_scenarios()` (scenarios are owned by their twin, not registered independently). Metrics are not yet implemented. Both registries are available for future use.

---

# Registry Interface

All registries share the same generic interface:

```python
from typing import Generic, TypeVar

T = TypeVar("T")

class PluginRegistry(Generic[T]):

    def register(self, plugin: T) -> None:
        """
        Register a plugin instance.

        Raises PluginValidationError if the plugin fails interface validation.
        Raises DuplicatePluginError if a plugin with the same id and version
        is already registered.
        """
        pass

    def get(self, plugin_id: str, version: str | None = None) -> T:
        """
        Retrieve a registered plugin by id.

        If version is None, returns the latest registered version.

        Raises PluginNotFoundError if no matching plugin is found.
        """
        pass

    def list(self) -> list[T]:
        """Return all registered plugins."""
        pass

    def contains(self, plugin_id: str) -> bool:
        pass
```

---

# Plugin Validation

When a plugin is registered, the registry validates it against its interface contract.

Validation checks:

- All required abstract methods are implemented.
- `metadata()` returns a dict containing the required keys (`*_id`, `name`, `version`, `description`).
- `version` is a valid semver string (e.g. `"1.0.0"`).
- No other plugin with the same `id + version` pair is already registered.

If any check fails, `PluginValidationError` is raised with a descriptive message.

---

# Registration at Startup

Plugins are registered during application startup, before the FastAPI app begins serving requests.

The recommended pattern is an explicit startup function in each plugin package:

```python
# epic_twins/mechanical/plugin.py

from epic_core.registry import twin_registry, sensor_registry, fault_registry
from .twin import MechanicalTwin
from .sensors import PositionSensor, VelocitySensor, TemperatureSensor
from .faults import IncreasedDampingFault, SensorBiasFault

def register():
    twin_registry.register(MechanicalTwin())
    sensor_registry.register(PositionSensor())
    sensor_registry.register(VelocitySensor())
    sensor_registry.register(TemperatureSensor())
    fault_registry.register(IncreasedDampingFault())
    fault_registry.register(SensorBiasFault())
```

The application startup module calls each plugin's `register()` function using FastAPI's `lifespan` pattern:

```python
# epic_api/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from epic_twins.mechanical.plugin import register as register_mechanical

@asynccontextmanager
async def lifespan(app: FastAPI):
    register_mechanical()
    # add more twin registrations here as new plugins are developed
    yield

app = FastAPI(lifespan=lifespan)
```

---

# Auto-Discovery via Entry Points

As an alternative to explicit registration, EPIC supports auto-discovery using Python package entry points.

A plugin package declares itself in `pyproject.toml`:

```toml
[project.entry-points."epic.plugins"]
mechanical = "epic_twins.mechanical.plugin:register"
```

The EPIC Core discovers and calls all registered entry points at startup:

```python
from importlib.metadata import entry_points

def discover_plugins():
    for ep in entry_points(group="epic.plugins"):
        register_fn = ep.load()
        register_fn()
```

This allows third-party digital twins to be installed as Python packages without modifying the EPIC Core or the application startup code.

---

# Versioning

The registry supports multiple versions of the same plugin simultaneously.

```python
sensor_registry.register(TemperatureSensor(version="1.0.0"))
sensor_registry.register(TemperatureSensor(version="1.1.0"))
```

When a contest is created, it pins specific plugin versions in the `contest_allowed_twins` junction table (see [Domain Model](domain-model.md)):

```text
contest_allowed_twins: (contest_id="forecast_2027", twin_id="mechanical_system", twin_version="1.0.0")
```

The simulation engine always requests the pinned version when loading plugins for a contest session:

```python
twin_version = get_pinned_version(session.contest_id, session.twin_id)
twin = twin_registry.get(session.twin_id, version=twin_version)
```

This ensures past contests remain reproducible even after a twin plugin is updated.

When no version is specified (e.g. during exploration outside a contest), the registry returns the latest version.

---

# Lookup by the Simulation Engine

The engine looks up plugins by id at session start:

```python
twin = twin_registry.get(session.twin_id)
scenario = next(s for s in twin.get_scenarios() if s.scenario_id == session.scenario_id)
```

Faults are looked up from the fault schedule:

```python
fault = fault_registry.get(entry["fault_id"])
```

If any lookup fails, the engine raises `PluginNotFoundError`, which causes the session to transition to `FAILED`.

---

# Registry and the API

The REST API endpoints for twins, sensors, and faults serve data directly from the registries:

```python
@router.get("/twins")
def list_twins():
    return [twin.metadata() for twin in twin_registry.list()]

@router.get("/twins/{twin_id}/sensors")
def list_sensors(twin_id: str):
    twin = twin_registry.get(twin_id)
    return [s.metadata() for s in twin.get_sensors()]

@router.get("/twins/{twin_id}/faults")
def list_faults(twin_id: str):
    twin = twin_registry.get(twin_id)
    return [f.metadata() for f in twin.get_faults()]
```

No database queries are required for metadata endpoints. The registry is the source of truth for plugin metadata.

---

# Thread Safety

The registry is populated at startup before any request is served and is read-only during normal operation.

No locking is required for reads.

If dynamic registration at runtime is ever needed in the future, registry writes must be protected with an `asyncio.Lock`.

---

# Design Requirement

The registry must be the only way for the Core and the API to access plugins.

No component outside `epic_core` should import plugin classes directly.

This guarantees that the Core never develops a hard dependency on any specific digital twin, sensor, or fault implementation.
