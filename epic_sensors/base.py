"""Base sensor implementation with configurable measurement pipeline."""

from __future__ import annotations

import random
from collections import deque

from epic_core.exceptions import PluginExecutionError
from epic_core.interfaces import Sensor, SimulationState
from epic_core.quantities import PhysicalQuantity


class _BaseSensor(Sensor):
    sensor_id_value: str
    name_value: str
    unit_value: str
    measured_quantity_value: PhysicalQuantity
    description_value: str

    def __init__(
        self,
        noise_std: float = 0.0,
        gain: float = 1.0,
        bias: float = 0.0,
        drift_rate: float = 0.0,
        min_value: float | None = None,
        max_value: float | None = None,
        quantization: float = 0.0,
        latency_steps: int = 0,
        p_false_reading: float = 0.0,
        p_outlier: float = 0.0,
        version: str = "1.0.0",
    ) -> None:
        self.noise_std = noise_std
        self.gain = gain
        self.bias = bias
        self.drift_rate = drift_rate
        self.min_value = min_value
        self.max_value = max_value
        self.quantization = quantization
        self.latency_steps = latency_steps
        self.p_false_reading = p_false_reading
        self.p_outlier = p_outlier
        self._version = version
        self._drift = 0.0
        self._latency_buffer: deque[float] = deque(maxlen=max(1, latency_steps + 1))

    @property
    def sensor_id(self) -> str:
        return self.sensor_id_value

    @property
    def name(self) -> str:
        return self.name_value

    @property
    def unit(self) -> str:
        return self.unit_value

    @property
    def measured_quantity(self) -> PhysicalQuantity:
        return self.measured_quantity_value

    def observe(self, state: SimulationState, dt: float = 0.0) -> float:
        raw = state.get_quantity(self.measured_quantity)
        if raw is None:
            raise PluginExecutionError(
                f"state does not provide quantity '{self.measured_quantity.value}'"
            )

        measurement = float(raw) * self.gain + self.bias
        if self.noise_std:
            measurement += random.gauss(0.0, self.noise_std)
        if self.drift_rate:
            self._drift += self.drift_rate * dt
            measurement += self._drift
        if self.min_value is not None:
            measurement = max(self.min_value, measurement)
        if self.max_value is not None:
            measurement = min(self.max_value, measurement)
        if self.quantization:
            measurement = round(measurement / self.quantization) * self.quantization

        if self.latency_steps > 0:
            self._latency_buffer.append(measurement)
            if len(self._latency_buffer) <= self.latency_steps:
                measurement = self._latency_buffer[0]
            else:
                measurement = self._latency_buffer.popleft()

        if random.random() < self.p_false_reading:
            if self.min_value is not None and self.max_value is not None:
                measurement = random.uniform(self.min_value, self.max_value)
            else:
                scale = 3.0 * (self.noise_std or 1.0)
                measurement = random.uniform(-scale, scale)
        if random.random() < self.p_outlier:
            measurement += random.choice((-1.0, 1.0)) * 10.0 * (self.noise_std or 1.0)
        return float(measurement)

    def metadata(self) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "name": self.name,
            "unit": self.unit,
            "measured_quantity": self.measured_quantity.value,
            "version": self._version,
            "description": self.description_value,
        }
