"""Fault descriptors and physics helpers for the electric motor twin."""

from __future__ import annotations

from epic.core.interfaces import FaultDescriptor, SimulationState


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


class OverheatingFault(_BaseFault):
    fault_id_value = "overheating"
    name_value = "Overheating"
    description_value = "Accelerates temperature rise and degrades output when hot"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.temperature += 0.8 * severity * dt
        if state.temperature > 80.0:
            degradation = min(0.25, 0.005 * severity * (state.temperature - 80.0))
            state.speed *= 1.0 - degradation
            state.torque *= 1.0 - degradation


class BearingFault(_BaseFault):
    fault_id_value = "bearing_fault"
    name_value = "Bearing Fault"
    description_value = "Adds speed ripple and heat from bearing damage"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.speed += 25.0 * severity * dt
        state.temperature += 0.25 * severity * dt


class VoltageImbalanceFault(_BaseFault):
    fault_id_value = "voltage_imbalance"
    name_value = "Voltage Imbalance"
    description_value = "Raises current and heat while reducing torque"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.current *= 1.0 + 0.12 * severity
        state.temperature += 0.35 * severity * dt
        state.torque *= 1.0 - 0.10 * severity
