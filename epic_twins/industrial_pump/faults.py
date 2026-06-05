"""Fault descriptors and physics helpers for the industrial pump twin."""

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
        pass


class CavitationFault(_BaseFault):
    fault_id_value = "cavitation"
    name_value = "Cavitation"
    description_value = "Reduces flow and raises vibration due to vapor bubbles"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.flow_rate *= max(0.0, 1.0 - 0.12 * severity)
        state.vibration += 1.5 * severity


class BearingWearFault(_BaseFault):
    fault_id_value = "bearing_wear"
    name_value = "Bearing Wear"
    description_value = "Increases wear, vibration, and temperature"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.wear = min(1.0, state.wear + 0.01 * severity * dt)
        state.vibration += 2.0 * severity + 4.0 * state.wear
        state.temperature += 0.2 * severity * dt


class FilterClogFault(_BaseFault):
    fault_id_value = "filter_clog"
    name_value = "Filter Clog"
    description_value = "Restricts flow and increases discharge pressure"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.flow_rate *= max(0.0, 1.0 - 0.18 * severity)
        state.pressure *= 1.0 + 0.10 * severity
