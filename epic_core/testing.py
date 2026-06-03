"""Test utilities for EPIC Core."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Iterator

import epic_core.registry as registry_module
from epic_core.interfaces import (
    DigitalTwin,
    Fault,
    Scenario,
    ScoringMetric,
    Sensor,
    SensorFault,
    SimulationState,
)
from epic_core.registry import PluginRegistry


@dataclass
class MockState(SimulationState):
    value: float = 0.0


class MockSensor(Sensor):
    def __init__(
        self,
        sensor_id: str = "mock_sensor",
        constant_value: float = 5.0,
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

    def observe(self, state) -> float:
        return float(self._constant_value)

    def metadata(self) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "name": self.name,
            "version": self._version,
            "description": "Mock sensor for tests",
        }


class MockFault(Fault):
    def __init__(self, fault_id: str = "mock_fault", version: str = "1.0.0") -> None:
        self._fault_id = fault_id
        self._version = version
        self._current_severity = 0.0
        self.apply_count = 0

    @property
    def fault_id(self) -> str:
        return self._fault_id

    @property
    def name(self) -> str:
        return "Mock Fault"

    @property
    def current_severity(self) -> float:
        return self._current_severity

    def activate(self, initial_severity: float = 1.0) -> None:
        self._current_severity = initial_severity

    def deactivate(self) -> None:
        self._current_severity = 0.0

    def apply(self, state: SimulationState, dt: float) -> None:
        self.apply_count += 1

    def metadata(self) -> dict:
        return {
            "fault_id": self.fault_id,
            "name": self.name,
            "version": self._version,
            "description": "Mock fault for tests",
        }


class MockSensorFault(SensorFault):
    def __init__(
        self,
        fault_id: str = "mock_sensor_fault",
        version: str = "1.0.0",
        target_sensor_ids: list[str] | None = None,
    ) -> None:
        self._fault_id = fault_id
        self._version = version
        self._target_sensor_ids = target_sensor_ids or []
        self._current_severity = 0.0

    @property
    def fault_id(self) -> str:
        return self._fault_id

    @property
    def name(self) -> str:
        return "Mock Sensor Fault"

    @property
    def current_severity(self) -> float:
        return self._current_severity

    @property
    def target_sensor_ids(self) -> list[str]:
        return self._target_sensor_ids

    def activate(self, initial_severity: float = 1.0) -> None:
        self._current_severity = initial_severity

    def deactivate(self) -> None:
        self._current_severity = 0.0

    def apply_to_measurement(self, measurement: float) -> float:
        return float(measurement + self.current_severity)

    def metadata(self) -> dict:
        return {
            "fault_id": self.fault_id,
            "name": self.name,
            "version": self._version,
            "description": "Mock sensor fault for tests",
        }


class MockScenario(Scenario):
    def __init__(
        self,
        scenario_id: str = "normal",
        fault_schedule: list[dict] | None = None,
        version: str = "1.0.0",
    ) -> None:
        self._scenario_id = scenario_id
        self._fault_schedule = fault_schedule or []
        self._version = version

    @property
    def scenario_id(self) -> str:
        return self._scenario_id

    @property
    def name(self) -> str:
        return "Mock Scenario"

    def initialize(self) -> dict:
        return {"initial_conditions": {"value": 0.0}}

    def get_fault_schedule(self) -> list[dict]:
        return self._fault_schedule

    def metadata(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "version": self._version,
            "description": "Mock scenario for tests",
        }


class MockTwin(DigitalTwin):
    def __init__(self, twin_id: str = "mock_twin", version: str = "1.0.0") -> None:
        self._twin_id = twin_id
        self._version = version
        self._sensor = MockSensor()
        self._fault = MockFault()
        self._scenario = MockScenario()

    @property
    def twin_id(self) -> str:
        return self._twin_id

    @property
    def name(self) -> str:
        return "Mock Twin"

    def create_initial_state(
        self, initial_conditions: dict | None = None
    ) -> SimulationState:
        value = 0.0
        if initial_conditions:
            value = float(initial_conditions.get("value", value))
        return MockState(value=value)

    def step(self, state: SimulationState, dt: float) -> SimulationState:
        return MockState(value=getattr(state, "value", 0.0) + dt)

    def get_sensors(self) -> list[Sensor]:
        return [self._sensor]

    def get_faults(self) -> list[Fault]:
        return [self._fault]

    def get_scenarios(self) -> list[Scenario]:
        return [self._scenario]

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
    faults: list[Fault] | None = None,
    scenarios: list[Scenario] | None = None,
    metrics: list[ScoringMetric] | None = None,
) -> Iterator[SimpleNamespace]:
    original = SimpleNamespace(
        twin=registry_module.twin_registry,
        sensor=registry_module.sensor_registry,
        fault=registry_module.fault_registry,
        scenario=registry_module.scenario_registry,
        metric=registry_module.metric_registry,
    )
    fresh = SimpleNamespace(
        twin=PluginRegistry(DigitalTwin),
        sensor=PluginRegistry(Sensor),
        fault=PluginRegistry(Fault),
        scenario=PluginRegistry(Scenario),
        metric=PluginRegistry(ScoringMetric),
    )

    registry_module.twin_registry = fresh.twin
    registry_module.sensor_registry = fresh.sensor
    registry_module.fault_registry = fresh.fault
    registry_module.scenario_registry = fresh.scenario
    registry_module.metric_registry = fresh.metric

    try:
        for plugin in twins or []:
            fresh.twin.register(plugin)
        for plugin in sensors or []:
            fresh.sensor.register(plugin)
        for plugin in faults or []:
            fresh.fault.register(plugin)
        for plugin in scenarios or []:
            fresh.scenario.register(plugin)
        for plugin in metrics or []:
            fresh.metric.register(plugin)
        yield fresh
    finally:
        registry_module.twin_registry = original.twin
        registry_module.sensor_registry = original.sensor
        registry_module.fault_registry = original.fault
        registry_module.scenario_registry = original.scenario
        registry_module.metric_registry = original.metric

