"""Plugin system interfaces for EPIC Core."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SimulationState(ABC):
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
    def create_initial_state(
        self, initial_conditions: dict | None = None
    ) -> SimulationState:
        pass

    @abstractmethod
    def step(self, state: SimulationState, dt: float) -> SimulationState:
        pass

    @abstractmethod
    def get_sensors(self) -> list[Sensor]:
        pass

    @abstractmethod
    def get_faults(self) -> list[Fault]:
        pass

    @abstractmethod
    def get_scenarios(self) -> list[Scenario]:
        pass

    @abstractmethod
    def metadata(self) -> dict:
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

    @abstractmethod
    def observe(self, state: SimulationState) -> float:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass


class Fault(ABC):
    @property
    @abstractmethod
    def fault_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def current_severity(self) -> float:
        pass

    @abstractmethod
    def activate(self, initial_severity: float = 1.0) -> None:
        pass

    @abstractmethod
    def deactivate(self) -> None:
        pass

    @abstractmethod
    def apply(self, state: SimulationState, dt: float) -> None:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass


class SensorFault(Fault):
    @property
    @abstractmethod
    def target_sensor_ids(self) -> list[str]:
        pass

    def apply(self, state: SimulationState, dt: float) -> None:
        pass

    @abstractmethod
    def apply_to_measurement(self, measurement: float) -> float:
        pass


class Scenario(ABC):
    @property
    @abstractmethod
    def scenario_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def initialize(self) -> dict:
        pass

    @abstractmethod
    def get_fault_schedule(self) -> list[dict]:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass


class OperatingProfile(ABC):
    @abstractmethod
    def value(self, t: float) -> float:
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
