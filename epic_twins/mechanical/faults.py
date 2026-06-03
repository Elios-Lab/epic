"""Faults for the mechanical twin."""

from __future__ import annotations

from epic_core.interfaces import Fault, SensorFault, SimulationState


class _BaseFault(Fault):
    fault_id_value: str
    name_value: str
    description_value: str

    def __init__(self, version: str = "1.0.0") -> None:
        self._version = version
        self._current_severity = 0.0
        self._active = False

    @property
    def fault_id(self) -> str:
        return self.fault_id_value

    @property
    def name(self) -> str:
        return self.name_value

    @property
    def current_severity(self) -> float:
        return self._current_severity

    def activate(self, initial_severity: float = 1.0) -> None:
        self._active = True
        self._current_severity = initial_severity

    def deactivate(self) -> None:
        self._active = False
        self._current_severity = 0.0

    def metadata(self) -> dict:
        return {
            "fault_id": self.fault_id,
            "name": self.name,
            "version": self._version,
            "description": self.description_value,
        }


class IncreasedDampingFault(_BaseFault):
    fault_id_value = "increased_damping"
    name_value = "Increased Damping"
    description_value = "Gradual increase in damping coefficient"

    def apply(self, state: SimulationState, dt: float) -> None:
        state.damping *= 1.0 + 0.1 * self.current_severity * dt
        if self._active:
            self._current_severity = min(1.0, self._current_severity + 0.05 * dt)


class ReducedStiffnessFault(_BaseFault):
    fault_id_value = "reduced_stiffness"
    name_value = "Reduced Stiffness"
    description_value = "Gradual reduction in stiffness coefficient"

    def apply(self, state: SimulationState, dt: float) -> None:
        state.stiffness *= 1.0 - 0.05 * self.current_severity * dt
        state.stiffness = max(1.0, state.stiffness)
        if self._active:
            self._current_severity = min(1.0, self._current_severity + 0.03 * dt)


class SensorBiasFault(SensorFault, _BaseFault):
    fault_id_value = "sensor_bias"
    name_value = "Sensor Bias"
    description_value = "Constant bias applied to sensor measurements"

    def __init__(
        self,
        target_sensor_ids: list[str] | None = None,
        bias: float = 0.5,
        version: str = "1.0.0",
    ) -> None:
        super().__init__(version)
        self._target_sensor_ids = target_sensor_ids or []
        self.bias = bias

    @property
    def target_sensor_ids(self) -> list[str]:
        return self._target_sensor_ids

    def apply_to_measurement(self, measurement: float) -> float:
        return float(measurement + self.bias * self.current_severity)
