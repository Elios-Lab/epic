"""Fault descriptors and physics helpers for the rotating machinery twin."""

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


class UnbalanceFault(_BaseFault):
    fault_id_value = "unbalance"
    name_value = "Rotor Unbalance"
    description_value = "Mass imbalance increases vibration with speed"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        speed_factor = max(0.0, state.speed / 1800.0)
        state.vibration += 2.5 * severity * speed_factor
        state.shaft_deflection += 0.02 * severity * speed_factor


class MisalignmentFault(_BaseFault):
    fault_id_value = "misalignment"
    name_value = "Shaft Misalignment"
    description_value = "Increases vibration, temperature, and power consumption"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.vibration += 1.8 * severity
        state.temperature += 0.35 * severity * dt
        state.power *= 1.0 + 0.08 * severity
        state.shaft_deflection += 0.015 * severity


class GearToothWearFault(_BaseFault):
    fault_id_value = "gear_tooth_wear"
    name_value = "Gear Tooth Wear"
    description_value = "Worn gear teeth raise vibration, heat, and shaft deflection"

    def apply(self, state: SimulationState, severity: float, dt: float) -> None:
        state.vibration += 1.2 * severity
        state.temperature += 0.25 * severity * dt
        state.shaft_deflection += 0.04 * severity * dt
