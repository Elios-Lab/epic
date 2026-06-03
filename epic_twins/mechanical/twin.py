"""Mass-spring-damper digital twin."""

from __future__ import annotations

import math
from dataclasses import dataclass

from epic_core.interfaces import (
    DigitalTwin,
    Fault,
    OperatingProfile,
    Scenario,
    Sensor,
    SimulationState,
)
from epic_twins.mechanical.faults import (
    IncreasedDampingFault,
    ReducedStiffnessFault,
    SensorBiasFault,
)
from epic_twins.mechanical.scenarios import (
    IncreasedDampingScenario,
    NormalOperationScenario,
    SensorBiasScenario,
)
from epic_twins.mechanical.sensors import (
    AccelerationSensor,
    PositionSensor,
    TemperatureSensor,
    VelocitySensor,
)


@dataclass
class MechanicalState(SimulationState):
    position: float
    velocity: float
    acceleration: float
    temperature: float
    mass: float = 1.0
    stiffness: float = 10.0
    damping: float = 0.5
    time: float = 0.0


class SinusoidalProfile(OperatingProfile):
    def __init__(self, amplitude: float = 0.5, frequency_hz: float = 1.0) -> None:
        self.amplitude = amplitude
        self.frequency_hz = frequency_hz

    def value(self, t: float) -> float:
        return self.amplitude * math.sin(2.0 * math.pi * self.frequency_hz * t)


class MechanicalTwin(DigitalTwin):
    def __init__(
        self,
        operating_profile: OperatingProfile | None = None,
        version: str = "1.0.0",
    ) -> None:
        self.operating_profile = operating_profile or SinusoidalProfile()
        self._version = version

    @property
    def twin_id(self) -> str:
        return "mechanical_system"

    @property
    def name(self) -> str:
        return "Mechanical System"

    def create_initial_state(
        self, initial_conditions: dict | None = None
    ) -> SimulationState:
        values = {
            "position": 0.1,
            "velocity": 0.0,
            "temperature": 20.0,
            "mass": 1.0,
            "stiffness": 10.0,
            "damping": 0.5,
            "time": 0.0,
        }
        if initial_conditions:
            values.update(initial_conditions)

        acceleration = self._acceleration(
            position=float(values["position"]),
            velocity=float(values["velocity"]),
            mass=float(values["mass"]),
            stiffness=float(values["stiffness"]),
            damping=float(values["damping"]),
            time=float(values["time"]),
        )
        return MechanicalState(
            position=float(values["position"]),
            velocity=float(values["velocity"]),
            acceleration=acceleration,
            temperature=float(values["temperature"]),
            mass=float(values["mass"]),
            stiffness=float(values["stiffness"]),
            damping=float(values["damping"]),
            time=float(values["time"]),
        )

    def step(self, state: SimulationState, dt: float) -> SimulationState:
        mechanical_state = _as_mechanical_state(state)
        acceleration = self._acceleration(
            position=mechanical_state.position,
            velocity=mechanical_state.velocity,
            mass=mechanical_state.mass,
            stiffness=mechanical_state.stiffness,
            damping=mechanical_state.damping,
            time=mechanical_state.time,
        )
        velocity = mechanical_state.velocity + acceleration * dt
        position = mechanical_state.position + mechanical_state.velocity * dt
        temperature = mechanical_state.temperature + (
            0.01 * abs(mechanical_state.damping * mechanical_state.velocity) * dt
        )
        time = mechanical_state.time + dt

        return MechanicalState(
            position=position,
            velocity=velocity,
            acceleration=acceleration,
            temperature=temperature,
            mass=mechanical_state.mass,
            stiffness=mechanical_state.stiffness,
            damping=mechanical_state.damping,
            time=time,
        )

    def get_sensors(self) -> list[Sensor]:
        return [
            PositionSensor(),
            VelocitySensor(),
            AccelerationSensor(),
            TemperatureSensor(),
        ]

    def get_faults(self) -> list[Fault]:
        return [
            IncreasedDampingFault(),
            ReducedStiffnessFault(),
            SensorBiasFault(),
        ]

    def get_scenarios(self) -> list[Scenario]:
        return [
            NormalOperationScenario(),
            IncreasedDampingScenario(),
            SensorBiasScenario(),
        ]

    def metadata(self) -> dict:
        return {
            "twin_id": self.twin_id,
            "name": self.name,
            "version": self._version,
            "description": "Simple mass-spring-damper mechanical system",
        }

    def _acceleration(
        self,
        position: float,
        velocity: float,
        mass: float,
        stiffness: float,
        damping: float,
        time: float,
    ) -> float:
        force = self.operating_profile.value(time)
        return (force - damping * velocity - stiffness * position) / mass


def _as_mechanical_state(state: SimulationState) -> MechanicalState:
    if not isinstance(state, MechanicalState):
        raise TypeError("state must be a MechanicalState")
    return state
