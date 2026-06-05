"""Test utilities for EPIC Core."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Iterator

import epic_core.registry as registry_module
from epic_core.interfaces import (
    DigitalTwin,
    FaultDescriptor,
    ScoringMetric,
    Sensor,
    SimulationState,
)
from epic_core.quantities import PhysicalQuantity
from epic_core.registry import PluginRegistry


@dataclass
class MockState(SimulationState):
    value: float = 0.0

    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        if quantity is PhysicalQuantity.LINEAR_POSITION:
            return self.value
        return None


class MockSensor(Sensor):
    def __init__(
        self,
        sensor_id: str = "mock_sensor",
        constant_value: float | None = 5.0,
        version: str = "1.0.0",
    ) -> None:
        self._sensor_id = sensor_id
        self._constant_value = constant_value
        self._version = version

    @property
    def sensor_id(self) -> str:
        return self._sensor_id

    @property
    def name(self) -> str:
        return "Mock Sensor"

    @property
    def unit(self) -> str:
        return "unit"

    @property
    def measured_quantity(self) -> PhysicalQuantity:
        return PhysicalQuantity.LINEAR_POSITION

    def observe(self, state: SimulationState, dt: float = 0.0) -> float:
        if self._constant_value is not None:
            return float(self._constant_value)
        value = state.get_quantity(self.measured_quantity)
        return 0.0 if value is None else float(value)

    def metadata(self) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "name": self.name,
            "unit": self.unit,
            "measured_quantity": self.measured_quantity.value,
            "version": self._version,
            "description": "Mock sensor for tests",
        }


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


@contextmanager
def test_registry_context(
    twins: list[DigitalTwin] | None = None,
    sensors: list[Sensor] | None = None,
    metrics: list[ScoringMetric] | None = None,
) -> Iterator[SimpleNamespace]:
    original = SimpleNamespace(
        twin=registry_module.twin_registry,
        sensor=registry_module.sensor_registry,
        metric=registry_module.metric_registry,
    )
    fresh = SimpleNamespace(
        twin=PluginRegistry(DigitalTwin, "twin_id"),
        sensor=PluginRegistry(Sensor, "sensor_id"),
        metric=PluginRegistry(ScoringMetric, "metric_id"),
    )

    registry_module.twin_registry = fresh.twin
    registry_module.sensor_registry = fresh.sensor
    registry_module.metric_registry = fresh.metric

    try:
        for plugin in twins or []:
            fresh.twin.register(plugin)
        for plugin in sensors or []:
            fresh.sensor.register(plugin)
        for plugin in metrics or []:
            fresh.metric.register(plugin)
        yield fresh
    finally:
        registry_module.twin_registry = original.twin
        registry_module.sensor_registry = original.sensor
        registry_module.metric_registry = original.metric
