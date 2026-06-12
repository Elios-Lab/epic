"""Industrial centrifugal pump digital twin."""

from __future__ import annotations

import math
from dataclasses import dataclass

from epic.core.interfaces import DigitalTwin, FaultDescriptor, SimulationState
from epic.core.quantities import PhysicalQuantity
from epic.twins.industrial_pump.faults import (
    BearingWearFault,
    CavitationFault,
    FilterClogFault,
)


@dataclass
class IndustrialPumpState(SimulationState):
    flow_rate: float
    pressure: float
    temperature: float
    vibration: float
    wear: float
    time: float

    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        return {
            PhysicalQuantity.FLOW_RATE: self.flow_rate,
            PhysicalQuantity.PRESSURE: self.pressure,
            PhysicalQuantity.TEMPERATURE: self.temperature,
            PhysicalQuantity.VIBRATION: self.vibration,
        }.get(quantity)


class IndustrialPumpTwin(DigitalTwin):
    _DEFAULTS = {
        "flow_rate": 120.0,
        "pressure": 4.0,
        "temperature": 35.0,
        "vibration": 1.0,
        "wear": 0.05,
    }

    def __init__(self, version: str = "1.0.0") -> None:
        self._version = version
        self._fault_objects: dict[
            str,
            CavitationFault | BearingWearFault | FilterClogFault,
        ] = {
            "cavitation": CavitationFault(),
            "bearing_wear": BearingWearFault(),
            "filter_clog": FilterClogFault(),
        }
        self._fault_schedule: list[dict] = []
        self._active_faults: dict[str, float] = {}
        self._t = 0.0
        self._nominal_flow_rate = float(self._DEFAULTS["flow_rate"])
        self._nominal_pressure = float(self._DEFAULTS["pressure"])

    @property
    def twin_id(self) -> str:
        return "industrial_pump"

    @property
    def name(self) -> str:
        return "Industrial Centrifugal Pump"

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
        self._nominal_flow_rate = float(values["flow_rate"])
        self._nominal_pressure = float(values["pressure"])
        return IndustrialPumpState(
            flow_rate=self._nominal_flow_rate,
            pressure=self._nominal_pressure,
            temperature=float(values["temperature"]),
            vibration=float(values["vibration"]),
            wear=max(0.0, min(1.0, float(values["wear"]))),
            time=0.0,
        )

    def step(self, state: SimulationState, dt: float) -> SimulationState:
        if not isinstance(state, IndustrialPumpState):
            raise TypeError("state must be IndustrialPumpState")

        self._t += dt
        self._tick_fault_schedule()

        flow_rate = self._nominal_flow_rate * (
            1.0 + 0.03 * math.sin(2.0 * math.pi * 0.2 * self._t)
        )
        pressure = self._nominal_pressure * (
            1.0 + 0.02 * math.sin(2.0 * math.pi * 0.2 * self._t + math.pi / 4.0)
        )
        wear = max(0.0, min(1.0, state.wear + 0.0005 * dt))
        temperature = state.temperature + (0.005 + 0.03 * wear) * dt
        vibration = 0.5 + 4.0 * wear + 0.15 * math.sin(2.0 * math.pi * self._t)
        new_state = IndustrialPumpState(
            flow_rate=flow_rate,
            pressure=pressure,
            temperature=temperature,
            vibration=vibration,
            wear=wear,
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

    def _apply_active_faults(self, state: IndustrialPumpState, dt: float) -> None:
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
            PhysicalQuantity.FLOW_RATE,
            PhysicalQuantity.PRESSURE,
            PhysicalQuantity.TEMPERATURE,
            PhysicalQuantity.VIBRATION,
        }

    def get_faults(self) -> list[FaultDescriptor]:
        return list(self._fault_objects.values())

    def metadata(self) -> dict:
        return {
            "twin_id": self.twin_id,
            "name": self.name,
            "version": self._version,
            "description": "Simple industrial centrifugal pump model",
        }
