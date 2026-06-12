"""Fault descriptors and physics helpers for the mass-spring-damper twin."""

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
