"""Fault descriptors and physics helpers for the smart building twin."""

from __future__ import annotations

from epic_core.kernel.interfaces import FaultDescriptor, SimulationState


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
        pass


class HVACFailureFault(_BaseFault):
    fault_id_value = "hvac_failure"
    name_value = "HVAC Failure"
    description_value = "Stops HVAC conditioning and raises indoor CO2"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.hvac_power *= 1.0 - severity
        state.co2 += 18.0 * severity * dt


class SensorDriftFault(_BaseFault):
    fault_id_value = "sensor_drift"
    name_value = "Sensor Drift"
    description_value = "Progressively biases temperature and humidity readings"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.temperature += 0.05 * severity * dt
        state.humidity += 0.08 * severity * dt


class OccupancySpikeFault(_BaseFault):
    fault_id_value = "occupancy_spike"
    name_value = "Occupancy Spike"
    description_value = "Adds sustained occupancy, CO2, and humidity load"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        added_people = int(round(25.0 * severity))
        state.occupancy += added_people
        state.co2 += 12.0 * added_people * dt
        state.humidity += 0.04 * added_people * dt
