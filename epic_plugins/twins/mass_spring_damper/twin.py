"""Mass-spring-damper digital twin."""

from __future__ import annotations

import math
from dataclasses import dataclass

from epic_core.kernel.interfaces import DigitalTwin, FaultDescriptor, SimulationState
from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.twins.mass_spring_damper.faults import (
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
        self._fault_objects: dict[
            str,
            IncreasedDampingFault | ReducedStiffnessFault | IncreasedFrictionFault,
        ] = {
            "increased_damping": IncreasedDampingFault(),
            "reduced_stiffness": ReducedStiffnessFault(),
            "increased_friction": IncreasedFrictionFault(),
        }
        self._fault_schedule: list[dict] = []
        self._active_faults: dict[str, float] = {}
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
        # Recompute acceleration with fault-modified stiffness/damping so that
        # state.acceleration is always consistent with the current system parameters.
        new_state.acceleration = self._acceleration(
            new_state.position,
            new_state.velocity,
            new_state.mass,
            new_state.stiffness,
            new_state.damping,
            new_state.time,
        )
        return new_state

    def _tick_fault_schedule(self) -> None:
        for entry in self._fault_schedule:
            fault_id = entry["fault_id"]
            active = self._t >= entry["start_time"] and (
                entry["end_time"] is None or self._t < entry["end_time"]
            )
            if active:
                self._active_faults[fault_id] = entry["severity"]
            else:
                self._active_faults.pop(fault_id, None)

    def _apply_active_faults(self, state: MassSpringDamperState, dt: float) -> None:
        for fault_id, severity in self._active_faults.items():
            fault_obj = self._fault_objects.get(fault_id)
            if fault_obj is not None:
                fault_obj.apply(state, severity, dt)

    def get_active_faults(self) -> list[dict]:
        return [
            {"fault_id": fault_id, "severity": severity}
            for fault_id, severity in self._active_faults.items()
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

    def initial_conditions_schema(self) -> list[dict]:
        return [
            {"key": "position",    "default": 0.1,  "unit": "m",     "kind": "state"},
            {"key": "velocity",    "default": 0.0,  "unit": "m/s",   "kind": "state"},
            {"key": "temperature", "default": 20.0, "unit": "°C",    "kind": "state"},
            {"key": "mass",        "default": 1.0,  "unit": "kg",    "kind": "parameter"},
            {"key": "stiffness",   "default": 10.0, "unit": "N/m",   "kind": "parameter"},
            {"key": "damping",     "default": 0.5,  "unit": "N·s/m", "kind": "parameter"},
        ]

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
