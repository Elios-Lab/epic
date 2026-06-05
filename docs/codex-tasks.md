# Codex Tasks — Architecture Alignment

This document contains self-contained prompts for Codex. Execute them in order — each task depends on the previous one.

---

## Task 1 — Rewrite `epic_core/interfaces.py`

**File:** `epic_core/interfaces.py`

Rewrite this file completely. The new content must define exactly the following four abstract classes, in this order. Do not add or remove any class.

```python
"""Core interfaces for EPIC."""

from __future__ import annotations

from abc import ABC, abstractmethod

from epic_core.quantities import PhysicalQuantity


class SimulationState(ABC):
    @abstractmethod
    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        """
        Return the current value for a physical quantity.
        Return None if this state does not model the requested quantity.
        """
        pass


class FaultDescriptor(ABC):
    """
    Lightweight descriptor for a fault supported by a digital twin.
    Used only for API listing and contest validation.
    The twin manages all fault activation and application internally.
    """

    @property
    @abstractmethod
    def fault_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        """
        Return fault metadata. Must include at minimum:
            {"fault_id": str, "name": str, "description": str}
        """
        pass


class DigitalTwin(ABC):

    @property
    @abstractmethod
    def twin_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def configure(
        self,
        initial_conditions: dict | None,
        fault_schedule: list[dict],
    ) -> SimulationState:
        """
        Called once by the engine before the simulation loop begins.

        The twin must:
        - Store the fault_schedule internally.
        - Build and return the initial SimulationState, applying
          initial_conditions overrides (if any) to its defaults.

        fault_schedule entries have the form:
            {
                "fault_id": str,
                "start_time": float,  # seconds from simulation start
                "end_time": float | None,  # None = until session ends
                "severity": float,    # [0.0, 1.0]
            }
        """
        pass

    @abstractmethod
    def step(self, state: SimulationState, dt: float) -> SimulationState:
        """
        Advance the simulation by one time step dt (seconds).

        The twin is responsible for:
        1. Advancing its internal simulation time by dt.
        2. Activating/deactivating faults per the stored schedule.
        3. Computing system dynamics.
        4. Applying active fault effects to the dynamics.
        5. Returning the new SimulationState (must not modify state in place).
        """
        pass

    @abstractmethod
    def get_active_faults(self) -> list[dict]:
        """
        Return the currently active faults.
        Called by the engine after each step() for label generation only.
        Must be read-only — must not modify twin state.

        Return format: [{"fault_id": str, "severity": float}, ...]
        """
        pass

    @abstractmethod
    def supported_quantities(self) -> set[PhysicalQuantity]:
        """Return the physical quantities this twin's state can provide."""
        pass

    @abstractmethod
    def get_faults(self) -> list[FaultDescriptor]:
        """Return descriptors for all faults this twin supports."""
        pass

    @abstractmethod
    def metadata(self) -> dict:
        """
        Return twin metadata. Must include at minimum:
            {"twin_id": str, "name": str, "version": str, "description": str}
        """
        pass


class Sensor(ABC):

    @property
    @abstractmethod
    def sensor_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def unit(self) -> str:
        pass

    @property
    @abstractmethod
    def measured_quantity(self) -> PhysicalQuantity:
        pass

    @abstractmethod
    def observe(self, state: SimulationState, dt: float = 0.0) -> float:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass


class ScoringMetric(ABC):

    @property
    @abstractmethod
    def metric_id(self) -> str:
        pass

    @property
    @abstractmethod
    def direction(self) -> str:
        """Return 'minimize' or 'maximize'."""
        pass

    @abstractmethod
    def compute(self, y_true, y_pred) -> float:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass
```

---

## Task 2 — Update `epic_core/testing.py`

**File:** `epic_core/testing.py`

Update this file to align with the new `DigitalTwin` interface. Keep `MockSensor`, `MockState`, `ScoringMetric` imports, and `test_registry_context` unchanged. Make these specific changes:

**Change 1:** Fix the import line to use `FaultDescriptor` instead of `Fault`:
```python
from epic_core.interfaces import DigitalTwin, FaultDescriptor, ScoringMetric, Sensor, SimulationState
```

**Change 2:** Replace the `MockFault` class entirely with this new version:
```python
class MockFaultDescriptor(FaultDescriptor):
    """Minimal FaultDescriptor for use in tests and mock twins."""

    def __init__(self, fault_id: str = "mock_fault") -> None:
        self._fault_id = fault_id

    @property
    def fault_id(self) -> str:
        return self._fault_id

    @property
    def name(self) -> str:
        return "Mock Fault"

    def metadata(self) -> dict:
        return {
            "fault_id": self.fault_id,
            "name": self.name,
            "description": "Mock fault descriptor for tests",
        }
```

**Change 3:** Replace the `MockTwin` class entirely with this new version:
```python
class MockTwin(DigitalTwin):
    """
    Minimal digital twin for engine and registry tests.

    State is a MockState with a single float value that increments by dt
    on each step. Supports one fault ('mock_fault') that activates per
    the fault schedule passed to configure().
    """

    def __init__(self, twin_id: str = "mock_twin", version: str = "1.0.0") -> None:
        self._twin_id = twin_id
        self._version = version
        self._fault_descriptor = MockFaultDescriptor()
        self._fault_schedule: list[dict] = []
        self._active_faults: dict[str, float] = {}
        self._t: float = 0.0
        self._fault_applied_count: int = 0

    @property
    def twin_id(self) -> str:
        return self._twin_id

    @property
    def name(self) -> str:
        return "Mock Twin"

    def configure(
        self, initial_conditions: dict | None, fault_schedule: list[dict]
    ) -> SimulationState:
        self._t = 0.0
        self._fault_schedule = fault_schedule or []
        self._active_faults = {}
        self._fault_applied_count = 0
        value = float((initial_conditions or {}).get("value", 0.0))
        return MockState(value=value)

    def step(self, state: SimulationState, dt: float) -> SimulationState:
        self._t += dt
        self._tick_faults()
        value = (state.get_quantity(PhysicalQuantity.LINEAR_POSITION) or 0.0) + dt
        if self._active_faults:
            self._fault_applied_count += 1
        return MockState(value=value)

    def _tick_faults(self) -> None:
        for entry in self._fault_schedule:
            fid = entry["fault_id"]
            active = self._t >= entry["start_time"] and (
                entry["end_time"] is None or self._t < entry["end_time"]
            )
            if active:
                self._active_faults[fid] = entry["severity"]
            else:
                self._active_faults.pop(fid, None)

    def get_active_faults(self) -> list[dict]:
        return [
            {"fault_id": fid, "severity": sev}
            for fid, sev in self._active_faults.items()
        ]

    def supported_quantities(self) -> set[PhysicalQuantity]:
        return {PhysicalQuantity.LINEAR_POSITION}

    def get_faults(self) -> list[FaultDescriptor]:
        return [self._fault_descriptor]

    def metadata(self) -> dict:
        return {
            "twin_id": self.twin_id,
            "name": self.name,
            "version": self._version,
            "description": "Mock twin for tests",
        }
```

**Change 4:** Remove any leftover reference to `MockFault` (old name), `MockScenario`, or `OperatingProfile`.

---

## Task 3 — Rewrite `epic_core/engine.py`

**File:** `epic_core/engine.py`

Rewrite `_run_loop` to use the new `DigitalTwin` interface. The full new `engine.py` must match this exactly:

```python
"""Domain-independent simulation engine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import numpy as np
from sqlalchemy import select

import epic_core.registry as registry_module
from epic_core.broadcaster import ContestBroadcaster
from epic_core.db.models import Contest, SensorObservation, SimulationSession
from epic_core.exceptions import PluginExecutionError, PluginNotFoundError


class SimulationEngine:
    def __init__(self, broadcaster: ContestBroadcaster | None = None) -> None:
        self._broadcaster = broadcaster

    async def run_session(self, session_id: str, db_factory) -> None:
        async with db_factory() as db:
            session = await self._load_session(db, session_id)
            session.status = "RUNNING"
            session.started_at = datetime.now(timezone.utc)
            await db.commit()

            try:
                await self._run_loop(session, db_factory)
            except Exception as exc:
                async with db_factory() as db2:
                    session2 = await self._load_session(db2, session_id)
                    session2.status = "FAILED"
                    session2.session_metadata = {
                        **(session2.session_metadata or {}),
                        "error": str(exc),
                    }
                    session2.ended_at = datetime.now(timezone.utc)
                    await db2.commit()
                return

    async def _load_session(self, db, session_id: str) -> SimulationSession:
        result = await db.execute(
            select(SimulationSession).where(SimulationSession.id == UUID(session_id))
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise PluginExecutionError(f"session '{session_id}' does not exist")
        return session

    async def _run_loop(self, session: SimulationSession, db_factory) -> None:
        async with db_factory() as db:
            contest = await self._load_contest(db, session.contest_id)

        # Load twin
        try:
            twin = registry_module.twin_registry.get(session.twin_id)
        except PluginNotFoundError as exc:
            raise PluginExecutionError(
                f"twin '{session.twin_id}' could not be loaded"
            ) from exc

        # Load and validate sensors
        contest_sensors = []
        supported = twin.supported_quantities()
        for cfg in contest.sensor_configs:
            sensor_id = cfg.get("sensor_id")
            try:
                sensor = registry_module.sensor_registry.get(sensor_id)
            except PluginNotFoundError as exc:
                raise PluginExecutionError(
                    f"sensor '{sensor_id}' could not be loaded"
                ) from exc
            if sensor.measured_quantity not in supported:
                raise PluginExecutionError(
                    f"sensor '{sensor_id}' is not compatible with twin '{twin.twin_id}'"
                )
            contest_sensors.append(sensor)

        # Validate fault schedule
        available_faults = {f.fault_id for f in twin.get_faults()}
        for entry in contest.fault_schedule:
            fid = entry.get("fault_id")
            if fid not in available_faults:
                raise PluginExecutionError(
                    f"fault '{fid}' is not available for twin '{twin.twin_id}'"
                )

        # Seed RNG
        if session.seed is not None:
            import random
            random.seed(session.seed)
            np.random.seed(session.seed)

        # Configure twin — returns initial state
        state = self._call_plugin(
            twin.twin_id,
            "configure",
            twin.configure,
            contest.initial_conditions,
            contest.fault_schedule,
        )

        dt = 1.0 / session.sampling_rate_hz
        sequence_id = 0
        commit_interval = 100

        async with db_factory() as db:
            contest_end_date = self._as_utc(contest.end_date)

            while (
                contest_end_date is not None
                and datetime.now(timezone.utc) < contest_end_date
            ):
                sequence_id += 1

                # Advance twin — fault management is entirely internal
                loop = asyncio.get_running_loop()
                new_state = await loop.run_in_executor(
                    None,
                    lambda s=state: self._call_plugin(
                        twin.twin_id, "step", twin.step, s, dt
                    ),
                )

                # Observe sensors
                sensors = {}
                for sensor in contest_sensors:
                    sensors[sensor.sensor_id] = self._call_plugin(
                        sensor.sensor_id, "observe", sensor.observe, new_state
                    )

                # Build labels from twin's active fault state
                active_faults = twin.get_active_faults()
                labels = {
                    "is_anomaly": len(active_faults) > 0,
                    "fault_ids": [f["fault_id"] for f in active_faults],
                    "severities": {
                        f["fault_id"]: f["severity"] for f in active_faults
                    },
                }

                timestamp = datetime.now(timezone.utc)
                observation = SensorObservation(
                    session_id=session.id,
                    sequence_id=sequence_id,
                    timestamp=timestamp,
                    sensors=sensors,
                    labels=labels,
                )
                db.add(observation)
                await self._broadcast(
                    str(session.contest_id),
                    {
                        "timestamp": timestamp.isoformat(),
                        "session_id": str(session.id),
                        "sequence_id": sequence_id,
                        "sensors": sensors,
                    },
                )
                state = new_state

                if sequence_id % commit_interval == 0:
                    await db.commit()
                    async with db_factory() as refresh_db:
                        refreshed = await self._load_contest(
                            refresh_db, session.contest_id
                        )
                    contest_end_date = self._as_utc(refreshed.end_date)

                await asyncio.sleep(dt)

            await db.commit()

        async with db_factory() as db:
            session = await self._load_session(db, str(session.id))
            session.status = "COMPLETED"
            session.ended_at = datetime.now(timezone.utc)
            await db.commit()

    def _call_plugin(self, plugin_id: str, method_name: str, method, *args):
        try:
            return method(*args)
        except PluginExecutionError:
            raise
        except Exception as exc:
            raise PluginExecutionError(
                f"plugin '{plugin_id}' raised an error in {method_name}()"
            ) from exc

    async def _load_contest(self, db, contest_id: UUID) -> Contest:
        result = await db.execute(select(Contest).where(Contest.id == contest_id))
        contest = result.scalar_one_or_none()
        if contest is None:
            raise PluginExecutionError(f"contest '{contest_id}' does not exist")
        return contest

    async def _broadcast(self, contest_id: str, payload: dict) -> None:
        if self._broadcaster:
            await self._broadcaster.broadcast(contest_id, payload)

    def _as_utc(self, value):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
```

Note: the key change is that `_run_loop` no longer has any fault activation/deactivation loop. Faults are managed entirely inside `twin.step()`. The engine only calls `twin.get_active_faults()` to build labels.

---

## Task 4 — Rewrite `epic_twins/mass_spring_damper/faults.py`

**File:** `epic_twins/mass_spring_damper/faults.py`

Rewrite this file. Fault classes must now implement `FaultDescriptor` (not `Fault`) for the Core interface. The actual physics of each fault (the `apply()` logic) becomes a private method used by the twin internally. Keep the same three fault classes and their physics — just reorganize their structure.

```python
"""Fault descriptors and physics helpers for the mass-spring-damper twin."""

from __future__ import annotations

from epic_core.interfaces import FaultDescriptor, SimulationState


class _BaseFault(FaultDescriptor):
    fault_id_value: str
    name_value: str
    description_value: str

    def __init__(self, version: str = "1.0.0") -> None:
        self._version = version

    @property
    def fault_id(self) -> str:
        return self.fault_id_value

    @property
    def name(self) -> str:
        return self.name_value

    def metadata(self) -> dict:
        return {
            "fault_id": self.fault_id,
            "name": self.name,
            "version": self._version,
            "description": self.description_value,
        }

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        """Apply fault effects to state. Called internally by the twin."""
        pass


class IncreasedDampingFault(_BaseFault):
    fault_id_value = "increased_damping"
    name_value = "Increased Damping"
    description_value = "Gradual increase in damping coefficient"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.damping *= 1.0 + 0.1 * severity * dt


class ReducedStiffnessFault(_BaseFault):
    fault_id_value = "reduced_stiffness"
    name_value = "Reduced Stiffness"
    description_value = "Gradual reduction in spring stiffness"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.stiffness = max(1.0, state.stiffness * (1.0 - 0.05 * severity * dt))


class IncreasedFrictionFault(_BaseFault):
    fault_id_value = "increased_friction"
    name_value = "Increased Friction"
    description_value = "Increased damping and heat from friction"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.temperature += 0.1 * severity * dt
        state.damping *= 1.0 + 0.02 * severity * dt
```

Note: `apply()` now takes `severity` as a parameter instead of reading it from internal state. Severity is passed by the twin from its active fault schedule.

---

## Task 5 — Rewrite `epic_twins/mass_spring_damper/twin.py`

**File:** `epic_twins/mass_spring_damper/twin.py`

Rewrite this file to implement the new `DigitalTwin` interface. The twin must manage its own fault schedule internally. Keep the same `MassSpringDamperState` dataclass and the same physics in `_acceleration()` and `step()`. Add `configure()` and `get_active_faults()`. Remove `create_initial_state()`.

```python
"""Mass-spring-damper digital twin."""

from __future__ import annotations

import math
from dataclasses import dataclass

from epic_core.interfaces import DigitalTwin, FaultDescriptor, SimulationState
from epic_core.quantities import PhysicalQuantity
from epic_twins.mass_spring_damper.faults import (
    IncreasedDampingFault,
    IncreasedFrictionFault,
    ReducedStiffnessFault,
)


@dataclass
class MassSpringDamperState(SimulationState):
    position: float
    velocity: float
    acceleration: float
    temperature: float
    mass: float
    stiffness: float
    damping: float
    time: float

    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        return {
            PhysicalQuantity.LINEAR_POSITION: self.position,
            PhysicalQuantity.LINEAR_VELOCITY: self.velocity,
            PhysicalQuantity.LINEAR_ACCELERATION: self.acceleration,
            PhysicalQuantity.TEMPERATURE: self.temperature,
        }.get(quantity)


class MassSpringDamperTwin(DigitalTwin):
    _DEFAULTS = {
        "position": 0.1,
        "velocity": 0.0,
        "temperature": 20.0,
        "mass": 1.0,
        "stiffness": 10.0,
        "damping": 0.5,
    }

    def __init__(self, version: str = "1.0.0") -> None:
        self._version = version
        self._fault_objects: dict[str, IncreasedDampingFault | ReducedStiffnessFault | IncreasedFrictionFault] = {
            "increased_damping": IncreasedDampingFault(),
            "reduced_stiffness": ReducedStiffnessFault(),
            "increased_friction": IncreasedFrictionFault(),
        }
        self._fault_schedule: list[dict] = []
        self._active_faults: dict[str, float] = {}  # fault_id -> severity
        self._t: float = 0.0

    @property
    def twin_id(self) -> str:
        return "mass_spring_damper"

    @property
    def name(self) -> str:
        return "Mass-Spring-Damper System"

    def configure(
        self,
        initial_conditions: dict | None,
        fault_schedule: list[dict],
    ) -> SimulationState:
        self._t = 0.0
        self._fault_schedule = fault_schedule or []
        self._active_faults = {}
        values = dict(self._DEFAULTS)
        values.update(initial_conditions or {})
        acceleration = self._acceleration(
            float(values["position"]),
            float(values["velocity"]),
            float(values["mass"]),
            float(values["stiffness"]),
            float(values["damping"]),
            0.0,
        )
        return MassSpringDamperState(
            position=float(values["position"]),
            velocity=float(values["velocity"]),
            acceleration=acceleration,
            temperature=float(values["temperature"]),
            mass=float(values["mass"]),
            stiffness=float(values["stiffness"]),
            damping=float(values["damping"]),
            time=0.0,
        )

    def step(self, state: SimulationState, dt: float) -> SimulationState:
        if not isinstance(state, MassSpringDamperState):
            raise TypeError("state must be MassSpringDamperState")

        self._t += dt
        self._tick_fault_schedule()

        new_time = state.time + dt
        new_velocity = state.velocity + state.acceleration * dt
        new_position = state.position + new_velocity * dt
        new_acceleration = self._acceleration(
            new_position,
            new_velocity,
            state.mass,
            state.stiffness,
            state.damping,
            new_time,
        )
        new_state = MassSpringDamperState(
            position=new_position,
            velocity=new_velocity,
            acceleration=new_acceleration,
            temperature=state.temperature,
            mass=state.mass,
            stiffness=state.stiffness,
            damping=state.damping,
            time=new_time,
        )

        self._apply_active_faults(new_state, dt)
        return new_state

    def _tick_fault_schedule(self) -> None:
        for entry in self._fault_schedule:
            fid = entry["fault_id"]
            active = self._t >= entry["start_time"] and (
                entry["end_time"] is None or self._t < entry["end_time"]
            )
            if active:
                self._active_faults[fid] = entry["severity"]
            else:
                self._active_faults.pop(fid, None)

    def _apply_active_faults(self, state: MassSpringDamperState, dt: float) -> None:
        for fid, severity in self._active_faults.items():
            fault_obj = self._fault_objects.get(fid)
            if fault_obj is not None:
                fault_obj.apply(state, severity, dt)

    def get_active_faults(self) -> list[dict]:
        return [
            {"fault_id": fid, "severity": sev}
            for fid, sev in self._active_faults.items()
        ]

    def supported_quantities(self) -> set[PhysicalQuantity]:
        return {
            PhysicalQuantity.LINEAR_POSITION,
            PhysicalQuantity.LINEAR_VELOCITY,
            PhysicalQuantity.LINEAR_ACCELERATION,
            PhysicalQuantity.TEMPERATURE,
        }

    def get_faults(self) -> list[FaultDescriptor]:
        return list(self._fault_objects.values())

    def metadata(self) -> dict:
        return {
            "twin_id": self.twin_id,
            "name": self.name,
            "version": self._version,
            "description": "Simple mechanical system (mass-spring-damper)",
        }

    def _acceleration(
        self,
        position: float,
        velocity: float,
        mass: float,
        stiffness: float,
        damping: float,
        time: float,
    ) -> float:
        force = 0.5 * math.sin(2.0 * math.pi * time)
        return (force - damping * velocity - stiffness * position) / mass
```

---

## Task 6 — Update `epic_core/registry.py`

**File:** `epic_core/registry.py`

Make two targeted changes:

**Change 1:** In the import block, replace `Fault` with `FaultDescriptor`:
```python
from epic_core.interfaces import (
    DigitalTwin,
    FaultDescriptor,
    ScoringMetric,
    Sensor,
)
```

**Change 2:** In `_validate()`, the registry infers the interface type by checking `isinstance`. `FaultDescriptor` is never registered globally (faults are twin-owned), so no registry change for faults is needed. However, update `_resolve_interface()` to only resolve `DigitalTwin`, `Sensor`, and `ScoringMetric` (unchanged — just remove any `Fault` reference if present).

**Change 3:** In `_id_key_for_interface()`, remove any `Fault`/`fault_id` branch if present.

---

## Task 7 — Rewrite `tests/core/test_interfaces.py`

**File:** `tests/core/test_interfaces.py`

Rewrite this file completely:

```python
import inspect

import pytest

from epic_core.interfaces import (
    DigitalTwin,
    FaultDescriptor,
    ScoringMetric,
    Sensor,
    SimulationState,
)
from epic_core.quantities import PhysicalQuantity
from epic_core.testing import MockFaultDescriptor, MockSensor, MockState, MockTwin


def test_interfaces_are_abstract():
    for interface in (DigitalTwin, Sensor, FaultDescriptor, ScoringMetric):
        assert inspect.isabstract(interface)


def test_mock_state_returns_supported_quantity():
    state = MockState(value=2.0)

    assert state.get_quantity(PhysicalQuantity.LINEAR_POSITION) == 2.0
    assert state.get_quantity(PhysicalQuantity.TEMPERATURE) is None


def test_mock_twin_configure_returns_state():
    twin = MockTwin()

    state = twin.configure({"value": 2.0}, [])

    assert isinstance(state, SimulationState)
    assert state.get_quantity(PhysicalQuantity.LINEAR_POSITION) == 2.0


def test_mock_twin_step_advances_value():
    twin = MockTwin()
    state = twin.configure(None, [])

    new_state = twin.step(state, 0.5)

    assert new_state is not state
    assert new_state.get_quantity(PhysicalQuantity.LINEAR_POSITION) == pytest.approx(0.5)


def test_mock_twin_get_active_faults_empty_with_no_schedule():
    twin = MockTwin()
    twin.configure(None, [])

    assert twin.get_active_faults() == []


def test_mock_twin_get_active_faults_after_schedule_activates():
    twin = MockTwin()
    schedule = [{"fault_id": "mock_fault", "start_time": 0.0, "end_time": None, "severity": 0.5}]
    twin.configure(None, schedule)
    twin.step(MockState(), 0.1)

    active = twin.get_active_faults()

    assert len(active) == 1
    assert active[0]["fault_id"] == "mock_fault"
    assert active[0]["severity"] == 0.5


def test_mock_twin_reports_no_active_faults_before_start_time():
    twin = MockTwin()
    schedule = [{"fault_id": "mock_fault", "start_time": 100.0, "end_time": None, "severity": 0.5}]
    twin.configure(None, schedule)
    twin.step(MockState(), 0.1)

    assert twin.get_active_faults() == []


def test_mock_twin_metadata_and_supported_quantities():
    twin = MockTwin()

    assert twin.metadata()["twin_id"] == twin.twin_id
    assert PhysicalQuantity.LINEAR_POSITION in twin.supported_quantities()
    assert isinstance(twin.get_faults()[0], FaultDescriptor)


def test_mock_sensor_observes_constant_value():
    sensor = MockSensor(sensor_id="sensor_a", constant_value=7.0)

    assert sensor.sensor_id == "sensor_a"
    assert sensor.name
    assert sensor.unit
    assert sensor.measured_quantity is PhysicalQuantity.LINEAR_POSITION
    assert sensor.observe(MockState(), dt=0.1) == 7.0
    assert sensor.metadata()["sensor_id"] == "sensor_a"


def test_mock_fault_descriptor_has_required_metadata():
    fault = MockFaultDescriptor()

    assert fault.fault_id
    assert fault.name
    assert "fault_id" in fault.metadata()
    assert "name" in fault.metadata()
    assert "description" in fault.metadata()


def test_incomplete_abstract_sensor_cannot_be_instantiated():
    class IncompleteSensor(Sensor):
        @property
        def sensor_id(self) -> str:
            return "incomplete"

        @property
        def name(self) -> str:
            return "Incomplete"

        @property
        def unit(self) -> str:
            return "unit"

        @property
        def measured_quantity(self) -> PhysicalQuantity:
            return PhysicalQuantity.LINEAR_POSITION

        def metadata(self) -> dict:
            return {}

    with pytest.raises(TypeError):
        IncompleteSensor()
```

---

## Task 8 — Rewrite `tests/core/test_engine.py`

**File:** `tests/core/test_engine.py`

Rewrite this file. Key changes from the old version:

- Remove `MockScenario`, `MockFaultScenario`, `ConfigurableMockTwin` — these are no longer needed.
- Remove `test_fault_scenario_applies_mock_fault` — replaced by label-based test.
- Remove `test_run_session_missing_scenario_sets_failed` — no scenario concept exists.
- The fault schedule is passed via `Contest.fault_schedule` which is passed to `twin.configure()` internally.
- Fault behaviour is verified through labels (`is_anomaly`, `fault_ids`), not through `apply_count`.
- `MockTwin` now handles the `mock_fault` schedule internally (see updated `testing.py`).

```python
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
    MockSensor,
    MockTwin,
    test_registry_context as registry_context,
)


class FailingTwin(MockTwin):
    def step(self, state, dt):
        raise RuntimeError("step failed")


class NoisyMockSensor(MockSensor):
    def __init__(self, sensor_id: str = "mock_sensor", noise_std: float = 1.0) -> None:
        super().__init__(sensor_id=sensor_id, constant_value=5.0)
        self.noise_std = noise_std

    def observe(self, state, dt: float = 0.0) -> float:
        return float(self._constant_value + np.random.normal(0.0, self.noise_std))


MOCK_FAULT_SCHEDULE = [
    {
        "fault_id": "mock_fault",
        "start_time": 0.0,
        "end_time": None,
        "severity": 0.5,
    }
]


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
    sensor_configs: list[dict] | None = None,
    fault_schedule: list[dict] | None = None,
    seed: int | None = None,
    seconds: float = 1.0,
) -> tuple[Contest, SimulationSession]:
    async with db_factory() as db:
        contest = Contest(
            name=name,
            twin_id=twin_id,
            sensor_configs=sensor_configs or [{"sensor_id": "mock_sensor"}],
            fault_schedule=fault_schedule or [],
            sampling_rate_hz=10.0,
            end_date=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        )
        db.add(contest)
        await db.commit()
        await db.refresh(contest)

        session = SimulationSession(
            contest_id=contest.id,
            twin_id=twin_id,
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

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    completed = await _get_session(engine_db_factory, session.id)
    assert completed.status == "COMPLETED"


@pytest.mark.asyncio
async def test_run_session_creates_observations(engine_db_factory):
    _, session = await _create_contest_and_session(engine_db_factory, "observations")

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)

    assert observations
    assert observations[0].session_id == session.id
    assert observations[0].sensors == {"mock_sensor": 5.0}


@pytest.mark.asyncio
async def test_run_session_observations_have_non_null_labels(engine_db_factory):
    _, session = await _create_contest_and_session(engine_db_factory, "labels")

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)

    assert observations
    assert all(obs.labels is not None for obs in observations)


@pytest.mark.asyncio
async def test_fault_schedule_produces_anomaly_labels(engine_db_factory):
    """Fault schedule passed to contest is forwarded to twin.configure() and
    active faults are reflected in ground-truth labels."""
    _, session = await _create_contest_and_session(
        engine_db_factory, "fault-labels", fault_schedule=MOCK_FAULT_SCHEDULE
    )

    with registry_context(twins=[MockTwin(twin_id="mock_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    observations = await _get_observations(engine_db_factory, session.id)

    assert observations[0].labels["is_anomaly"] is True
    assert "mock_fault" in observations[0].labels["fault_ids"]


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
async def test_run_session_missing_sensor_sets_failed(engine_db_factory):
    _, session = await _create_contest_and_session(
        engine_db_factory,
        "missing-sensor",
        sensor_configs=[{"sensor_id": "missing_sensor"}],
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

    with registry_context(twins=[FailingTwin(twin_id="failing_twin")], sensors=[MockSensor()]):
        await SimulationEngine().run_session(str(session.id), engine_db_factory)

    failed = await _get_session(engine_db_factory, session.id)
    assert failed.status == "FAILED"
    assert "error" in failed.session_metadata


@pytest.mark.asyncio
async def test_run_session_seed_reproduces_noisy_sensor_values(engine_db_factory):
    first_twin = MockTwin(twin_id="first_seed_twin")
    second_twin = MockTwin(twin_id="second_seed_twin")

    with registry_context(twins=[first_twin, second_twin], sensors=[NoisyMockSensor()]):
        _, first_session = await _create_contest_and_session(
            engine_db_factory, "first-seed", twin_id="first_seed_twin", seed=42
        )
        await SimulationEngine().run_session(str(first_session.id), engine_db_factory)

        _, second_session = await _create_contest_and_session(
            engine_db_factory, "second-seed", twin_id="second_seed_twin", seed=42
        )
        await SimulationEngine().run_session(str(second_session.id), engine_db_factory)

    first_obs = (await _get_observations(engine_db_factory, first_session.id))[0]
    second_obs = (await _get_observations(engine_db_factory, second_session.id))[0]

    assert first_obs.sensors["mock_sensor"] == second_obs.sensors["mock_sensor"]
```

---

## Task 9 — Rewrite `tests/twins/mass_spring_damper/test_twin.py`

**File:** `tests/twins/mass_spring_damper/test_twin.py`

Rewrite this file to use the new `configure()` interface. Remove `create_initial_state()` calls. Add tests for fault schedule management via `configure()` and `get_active_faults()`.

```python
import pytest

import epic_core.registry as registry_module
from epic_core.interfaces import FaultDescriptor, SimulationState
from epic_core.quantities import PhysicalQuantity
from epic_core.testing import MockState, test_registry_context as registry_context
from epic_twins.mass_spring_damper.plugin import register
from epic_twins.mass_spring_damper.twin import MassSpringDamperState, MassSpringDamperTwin


def test_configure_returns_state_with_initial_conditions():
    state = MassSpringDamperTwin().configure({"position": 0.2}, [])

    assert isinstance(state, SimulationState)
    assert isinstance(state, MassSpringDamperState)
    assert state.position == pytest.approx(0.2)
    assert state.time == 0.0
    assert state.get_quantity(PhysicalQuantity.LINEAR_POSITION) == pytest.approx(0.2)


def test_configure_uses_defaults_when_no_initial_conditions():
    state = MassSpringDamperTwin().configure(None, [])

    assert isinstance(state, MassSpringDamperState)
    assert state.position == pytest.approx(0.1)


def test_step_returns_new_state_and_advances_time():
    twin = MassSpringDamperTwin()
    state = twin.configure(None, [])

    new_state = twin.step(state, 0.1)

    assert new_state is not state
    assert new_state.time == pytest.approx(0.1)


def test_step_rejects_non_mass_spring_damper_state():
    with pytest.raises(TypeError):
        MassSpringDamperTwin().configure(None, [])
        MassSpringDamperTwin().step(MockState(), 0.1)


def test_get_active_faults_empty_before_schedule_start():
    twin = MassSpringDamperTwin()
    schedule = [{"fault_id": "increased_damping", "start_time": 100.0, "end_time": None, "severity": 0.5}]
    state = twin.configure(None, schedule)
    twin.step(state, 0.1)

    assert twin.get_active_faults() == []


def test_fault_activates_at_scheduled_time():
    twin = MassSpringDamperTwin()
    schedule = [{"fault_id": "increased_damping", "start_time": 0.0, "end_time": None, "severity": 0.3}]
    state = twin.configure(None, schedule)
    twin.step(state, 0.1)

    active = twin.get_active_faults()

    assert len(active) == 1
    assert active[0]["fault_id"] == "increased_damping"
    assert active[0]["severity"] == pytest.approx(0.3)


def test_fault_deactivates_after_end_time():
    twin = MassSpringDamperTwin()
    schedule = [{"fault_id": "increased_damping", "start_time": 0.0, "end_time": 0.05, "severity": 0.5}]
    state = twin.configure(None, schedule)
    twin.step(state, 0.1)  # t=0.1 > end_time=0.05

    assert twin.get_active_faults() == []


def test_fault_alters_damping_during_step():
    twin = MassSpringDamperTwin()
    schedule = [{"fault_id": "increased_damping", "start_time": 0.0, "end_time": None, "severity": 1.0}]
    state_no_fault = MassSpringDamperTwin().configure(None, [])
    state_with_fault = twin.configure(None, schedule)

    for _ in range(10):
        state_no_fault = MassSpringDamperTwin().step(state_no_fault, 0.1)
        state_with_fault = twin.step(state_with_fault, 0.1)

    assert state_with_fault.damping > state_no_fault.damping


def test_twin_metadata_supported_quantities_and_faults():
    twin = MassSpringDamperTwin()

    assert twin.metadata()["twin_id"] == "mass_spring_damper"
    assert PhysicalQuantity.LINEAR_POSITION in twin.supported_quantities()
    assert PhysicalQuantity.TEMPERATURE in twin.supported_quantities()
    assert all(isinstance(f, FaultDescriptor) for f in twin.get_faults())
    fault_ids = {f.fault_id for f in twin.get_faults()}
    assert "increased_damping" in fault_ids
    assert "reduced_stiffness" in fault_ids
    assert "increased_friction" in fault_ids


def test_plugin_registers_mass_spring_damper_twin():
    with registry_context():
        register()

        assert registry_module.twin_registry.contains("mass_spring_damper")
```

---

## Task 10 — Rewrite `tests/twins/mass_spring_damper/test_faults.py`

**File:** `tests/twins/mass_spring_damper/test_faults.py`

Rewrite this file. Faults no longer have `activate()`, `deactivate()`, or `current_severity`. Tests must verify: metadata is correct, and `apply()` (the private physics helper, called with explicit severity) produces the expected physical effects.

```python
from epic_core.interfaces import FaultDescriptor
from epic_core.quantities import PhysicalQuantity
from epic_twins.mass_spring_damper.faults import (
    IncreasedDampingFault,
    IncreasedFrictionFault,
    ReducedStiffnessFault,
)
from epic_twins.mass_spring_damper.twin import MassSpringDamperState


def _state() -> MassSpringDamperState:
    return MassSpringDamperState(
        position=0.1,
        velocity=1.0,
        acceleration=0.0,
        temperature=20.0,
        mass=1.0,
        stiffness=10.0,
        damping=0.5,
        time=0.0,
    )


def test_faults_implement_fault_descriptor():
    for fault in (IncreasedDampingFault(), ReducedStiffnessFault(), IncreasedFrictionFault()):
        assert isinstance(fault, FaultDescriptor)


def test_faults_have_required_metadata():
    for fault in (IncreasedDampingFault(), ReducedStiffnessFault(), IncreasedFrictionFault()):
        md = fault.metadata()
        assert md["fault_id"]
        assert md["name"]
        assert md["version"]
        assert md["description"]


def test_increased_damping_raises_damping():
    state = _state()
    IncreasedDampingFault().apply(state, severity=1.0, dt=1.0)

    assert state.damping > 0.5


def test_reduced_stiffness_lowers_stiffness():
    state = _state()
    ReducedStiffnessFault().apply(state, severity=1.0, dt=1.0)

    assert state.stiffness < 10.0


def test_increased_friction_raises_temperature_and_damping():
    state = _state()
    IncreasedFrictionFault().apply(state, severity=1.0, dt=1.0)

    assert state.temperature > 20.0
    assert state.damping > 0.5
    assert state.get_quantity(PhysicalQuantity.TEMPERATURE) == state.temperature


def test_zero_severity_has_no_effect():
    state = _state()
    IncreasedDampingFault().apply(state, severity=0.0, dt=1.0)

    assert state.damping == 0.5
```

---

## Execution Notes

Run tasks **in order**. After completing tasks 1–5, run the full test suite to confirm the core and twin tests pass before moving to test rewrites (tasks 7–10).

```bash
cd /path/to/EPIC
uv run pytest tests/ -x -q
```

Expected final state: all tests pass, no imports of `Fault`, `Scenario`, `SensorFault`, `OperatingProfile`, `MockScenario`, or `create_initial_state` remain in any file outside of `.venv/`.
