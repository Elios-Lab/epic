"""Smart building floor digital twin."""

from __future__ import annotations

import math
from dataclasses import dataclass

from epic_core.kernel.interfaces import DigitalTwin, FaultDescriptor, SimulationState
from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.twins.smart_building.faults import (
    HVACFailureFault,
    OccupancySpikeFault,
    SensorDriftFault,
)


@dataclass
class SmartBuildingState(SimulationState):
    temperature: float
    humidity: float
    co2: float
    occupancy: int
    hvac_power: float
    time: float

    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        return {
            PhysicalQuantity.TEMPERATURE: self.temperature,
            PhysicalQuantity.HUMIDITY: self.humidity,
            PhysicalQuantity.CO2_CONCENTRATION: self.co2,
            PhysicalQuantity.OCCUPANCY: float(self.occupancy),
        }.get(quantity)


class SmartBuildingTwin(DigitalTwin):
    _DEFAULTS = {
        "temperature": 22.0,
        "humidity": 45.0,
        "co2": 650.0,
        "occupancy": 20,
        "hvac_power": 3500.0,
        "target_temperature": 22.0,
        "outdoor_temperature": 30.0,
    }

    def __init__(self, version: str = "1.0.0") -> None:
        self._version = version
        self._fault_objects: dict[
            str,
            HVACFailureFault | SensorDriftFault | OccupancySpikeFault,
        ] = {
            "hvac_failure": HVACFailureFault(),
            "sensor_drift": SensorDriftFault(),
            "occupancy_spike": OccupancySpikeFault(),
        }
        self._fault_schedule: list[dict] = []
        self._active_faults: dict[str, float] = {}
        self._t = 0.0
        self._nominal_occupancy = int(self._DEFAULTS["occupancy"])
        self._nominal_hvac_power = float(self._DEFAULTS["hvac_power"])
        self._target_temperature = float(self._DEFAULTS["target_temperature"])
        self._outdoor_temperature = float(self._DEFAULTS["outdoor_temperature"])

    @property
    def twin_id(self) -> str:
        return "smart_building"

    @property
    def name(self) -> str:
        return "Smart Commercial Building Floor"

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
        self._nominal_occupancy = int(values["occupancy"])
        self._nominal_hvac_power = float(values["hvac_power"])
        self._target_temperature = float(values["target_temperature"])
        self._outdoor_temperature = float(values["outdoor_temperature"])
        return SmartBuildingState(
            temperature=float(values["temperature"]),
            humidity=float(values["humidity"]),
            co2=float(values["co2"]),
            occupancy=self._nominal_occupancy,
            hvac_power=self._nominal_hvac_power,
            time=0.0,
        )

    def step(self, state: SimulationState, dt: float) -> SimulationState:
        if not isinstance(state, SmartBuildingState):
            raise TypeError("state must be SmartBuildingState")

        self._t += dt
        self._tick_fault_schedule()

        occupancy = max(
            0,
            int(round(self._nominal_occupancy + 3.0 * math.sin(2.0 * math.pi * self._t / 8.0))),
        )
        temperature_error = state.temperature - self._target_temperature
        hvac_fraction = min(1.0, abs(temperature_error) / 4.0)
        hvac_power = self._nominal_hvac_power * hvac_fraction
        envelope_drift = 0.03 * (self._outdoor_temperature - state.temperature) * dt
        hvac_correction = 0.12 * temperature_error * dt
        temperature = state.temperature + envelope_drift - hvac_correction
        co2 = max(
            400.0,
            state.co2 + (4.0 * occupancy - 0.025 * (state.co2 - 420.0)) * dt,
        )
        humidity = max(
            20.0,
            min(80.0, state.humidity + (0.015 * occupancy - 0.0015 * hvac_power) * dt),
        )
        new_state = SmartBuildingState(
            temperature=temperature,
            humidity=humidity,
            co2=co2,
            occupancy=occupancy,
            hvac_power=hvac_power,
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

    def _apply_active_faults(self, state: SmartBuildingState, dt: float) -> None:
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
            PhysicalQuantity.TEMPERATURE,
            PhysicalQuantity.HUMIDITY,
            PhysicalQuantity.CO2_CONCENTRATION,
            PhysicalQuantity.OCCUPANCY,
        }

    def get_faults(self) -> list[FaultDescriptor]:
        return list(self._fault_objects.values())

    def metadata(self) -> dict:
        return {
            "twin_id": self.twin_id,
            "name": self.name,
            "version": self._version,
            "description": "Simple smart building HVAC floor model",
        }
