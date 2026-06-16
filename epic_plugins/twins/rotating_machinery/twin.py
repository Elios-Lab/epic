"""Rotating shaft and gearbox digital twin."""

from __future__ import annotations

import math
from dataclasses import dataclass

from epic_core.kernel.interfaces import DigitalTwin, FaultDescriptor, SimulationState
from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.twins.rotating_machinery.faults import (
    GearToothWearFault,
    MisalignmentFault,
    UnbalanceFault,
)


@dataclass
class RotatingMachineryState(SimulationState):
    speed: float
    vibration: float
    temperature: float
    power: float
    shaft_deflection: float
    time: float

    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        return {
            PhysicalQuantity.ROTATIONAL_SPEED: self.speed,
            PhysicalQuantity.VIBRATION: self.vibration,
            PhysicalQuantity.TEMPERATURE: self.temperature,
            PhysicalQuantity.POWER: self.power,
        }.get(quantity)


class RotatingMachineryTwin(DigitalTwin):
    _DEFAULTS = {
        "speed": 1800.0,
        "vibration": 1.2,
        "temperature": 45.0,
        "power": 75000.0,
        "shaft_deflection": 0.05,
    }

    def __init__(self, version: str = "1.0.0") -> None:
        self._version = version
        self._fault_objects: dict[
            str,
            UnbalanceFault | MisalignmentFault | GearToothWearFault,
        ] = {
            "unbalance": UnbalanceFault(),
            "misalignment": MisalignmentFault(),
            "gear_tooth_wear": GearToothWearFault(),
        }
        self._fault_schedule: list[dict] = []
        self._active_faults: dict[str, float] = {}
        self._t = 0.0
        self._nominal_speed = float(self._DEFAULTS["speed"])
        self._nominal_power = float(self._DEFAULTS["power"])
        self._nominal_vibration = float(self._DEFAULTS["vibration"])

    @property
    def twin_id(self) -> str:
        return "rotating_machinery"

    @property
    def name(self) -> str:
        return "Rotating Shaft and Gearbox"

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
        self._nominal_speed = float(values["speed"])
        self._nominal_power = float(values["power"])
        self._nominal_vibration = float(values["vibration"])
        return RotatingMachineryState(
            speed=self._nominal_speed,
            vibration=self._nominal_vibration,
            temperature=float(values["temperature"]),
            power=self._nominal_power,
            shaft_deflection=float(values["shaft_deflection"]),
            time=0.0,
        )

    def step(self, state: SimulationState, dt: float) -> SimulationState:
        if not isinstance(state, RotatingMachineryState):
            raise TypeError("state must be RotatingMachineryState")

        self._t += dt
        self._tick_fault_schedule()

        load_factor = 1.0 + 0.08 * math.sin(2.0 * math.pi * 0.15 * self._t)
        speed = self._nominal_speed * (
            1.0 + 0.004 * math.sin(2.0 * math.pi * 0.5 * self._t)
        )
        power = self._nominal_power * load_factor
        vibration = self._nominal_vibration + 0.18 * math.sin(
            2.0 * math.pi * 1.5 * self._t
        )
        temperature = state.temperature + (0.01 + 0.025 * load_factor) * dt
        shaft_deflection = float(self._DEFAULTS["shaft_deflection"]) + 0.002 * math.sin(
            2.0 * math.pi * 0.3 * self._t
        )
        new_state = RotatingMachineryState(
            speed=speed,
            vibration=vibration,
            temperature=temperature,
            power=power,
            shaft_deflection=shaft_deflection,
            time=state.time + dt,
        )
        self._apply_active_faults(new_state, dt)
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

    def _apply_active_faults(self, state: RotatingMachineryState, dt: float) -> None:
        for fault_id, severity in self._active_faults.items():
            fault = self._fault_objects.get(fault_id)
            if fault is not None:
                fault.apply(state, severity, dt)

    def get_active_faults(self) -> list[dict]:
        return [
            {"fault_id": fault_id, "severity": severity}
            for fault_id, severity in self._active_faults.items()
        ]

    def supported_quantities(self) -> set[PhysicalQuantity]:
        return {
            PhysicalQuantity.ROTATIONAL_SPEED,
            PhysicalQuantity.VIBRATION,
            PhysicalQuantity.TEMPERATURE,
            PhysicalQuantity.POWER,
        }

    def get_faults(self) -> list[FaultDescriptor]:
        return list(self._fault_objects.values())

    def metadata(self) -> dict:
        return {
            "twin_id": self.twin_id,
            "name": self.name,
            "version": self._version,
            "description": "Simple rotating shaft and gearbox model",
        }
