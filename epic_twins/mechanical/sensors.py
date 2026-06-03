"""Scalar sensors for the mechanical twin."""

from __future__ import annotations

import numpy as np

from epic_core.interfaces import Sensor, SimulationState


class _MechanicalSensor(Sensor):
    sensor_id_value: str
    name_value: str
    unit_value: str
    field_name: str

    def __init__(self, noise_std: float = 0.0, version: str = "1.0.0") -> None:
        self.noise_std = noise_std
        self._version = version

    @property
    def sensor_id(self) -> str:
        return self.sensor_id_value

    @property
    def name(self) -> str:
        return self.name_value

    @property
    def unit(self) -> str:
        return self.unit_value

    def observe(self, state: SimulationState) -> float:
        value = float(getattr(state, self.field_name))
        if self.noise_std == 0.0:
            return value
        return float(value + np.random.normal(0.0, self.noise_std))

    def metadata(self) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "name": self.name,
            "version": self._version,
            "description": f"{self.name} for mechanical system",
        }


class PositionSensor(_MechanicalSensor):
    sensor_id_value = "position"
    name_value = "Position Sensor"
    unit_value = "m"
    field_name = "position"


class VelocitySensor(_MechanicalSensor):
    sensor_id_value = "velocity"
    name_value = "Velocity Sensor"
    unit_value = "m/s"
    field_name = "velocity"


class AccelerationSensor(_MechanicalSensor):
    sensor_id_value = "acceleration"
    name_value = "Acceleration Sensor"
    unit_value = "m/s²"
    field_name = "acceleration"


class TemperatureSensor(_MechanicalSensor):
    sensor_id_value = "temperature"
    name_value = "Temperature Sensor"
    unit_value = "°C"
    field_name = "temperature"

