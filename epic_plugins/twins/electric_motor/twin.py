"""Three-phase induction motor digital twin."""

from __future__ import annotations

import math
from dataclasses import dataclass

from epic_core.kernel.interfaces import DigitalTwin, FaultDescriptor, SimulationState
from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.twins.electric_motor.faults import (
    BearingFault,
    OverheatingFault,
    VoltageImbalanceFault,
)


@dataclass
class ElectricMotorState(SimulationState):
    current: float
    voltage: float
    speed: float
    temperature: float
    torque: float
    time: float

    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        return {
            PhysicalQuantity.CURRENT: self.current,
            PhysicalQuantity.VOLTAGE: self.voltage,
            PhysicalQuantity.ROTATIONAL_SPEED: self.speed,
            PhysicalQuantity.TEMPERATURE: self.temperature,
            PhysicalQuantity.TORQUE: self.torque,
        }.get(quantity)


class ElectricMotorTwin(DigitalTwin):
    _DEFAULTS = {
        "current": 12.0,
        "voltage": 400.0,
        "speed": 1450.0,
        "temperature": 40.0,
        "torque": 80.0,
    }

    def __init__(self, version: str = "1.0.0") -> None:
        self._version = version
        self._fault_objects: dict[
            str,
            OverheatingFault | BearingFault | VoltageImbalanceFault,
        ] = {
            "overheating": OverheatingFault(),
            "bearing_fault": BearingFault(),
            "voltage_imbalance": VoltageImbalanceFault(),
        }
        self._fault_schedule: list[dict] = []
        self._active_faults: dict[str, float] = {}
        self._t = 0.0
        self._nominal_current = float(self._DEFAULTS["current"])
        self._nominal_voltage = float(self._DEFAULTS["voltage"])
        self._nominal_speed = float(self._DEFAULTS["speed"])
        self._nominal_torque = float(self._DEFAULTS["torque"])
        self._supply_frequency_hz = 50.0

    @property
    def twin_id(self) -> str:
        return "electric_motor"

    @property
    def name(self) -> str:
        return "Three-Phase Induction Motor"

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
        self._nominal_current = float(values["current"])
        self._nominal_voltage = float(values["voltage"])
        self._nominal_speed = float(values["speed"])
        self._nominal_torque = float(values["torque"])
        return ElectricMotorState(
            current=self._nominal_current,
            voltage=self._nominal_voltage,
            speed=self._nominal_speed,
            temperature=float(values["temperature"]),
            torque=self._nominal_torque,
            time=0.0,
        )

    def step(self, state: SimulationState, dt: float) -> SimulationState:
        if not isinstance(state, ElectricMotorState):
            raise TypeError("state must be ElectricMotorState")

        self._t += dt
        self._tick_fault_schedule()

        supply_phase = 2.0 * math.pi * self._supply_frequency_hz * self._t
        load_phase = 2.0 * math.pi * 0.5 * self._t
        current = self._nominal_current * (1.0 + 0.04 * math.sin(supply_phase))
        voltage = self._nominal_voltage * (
            1.0 + 0.015 * math.sin(supply_phase + math.pi / 3.0)
        )
        speed = self._nominal_speed * (1.0 + 0.01 * math.sin(load_phase))
        torque = self._nominal_torque * (
            1.0 + 0.03 * math.sin(load_phase + math.pi / 5.0)
        )
        load_factor = max(0.0, torque / self._nominal_torque)
        temperature = state.temperature + (0.02 + 0.03 * load_factor) * dt
        new_state = ElectricMotorState(
            current=current,
            voltage=voltage,
            speed=speed,
            temperature=temperature,
            torque=torque,
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

    def _apply_active_faults(self, state: ElectricMotorState, dt: float) -> None:
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
            PhysicalQuantity.CURRENT,
            PhysicalQuantity.VOLTAGE,
            PhysicalQuantity.ROTATIONAL_SPEED,
            PhysicalQuantity.TEMPERATURE,
            PhysicalQuantity.TORQUE,
        }

    def get_faults(self) -> list[FaultDescriptor]:
        return list(self._fault_objects.values())

    def metadata(self) -> dict:
        return {
            "twin_id": self.twin_id,
            "name": self.name,
            "version": self._version,
            "description": "Simple three-phase induction motor model",
        }
