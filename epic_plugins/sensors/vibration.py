"""Vibration sensor."""

from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.sensors.base import _BaseSensor


class VibrationSensor(_BaseSensor):
    sensor_id_value = "vibration"
    name_value = "Vibration Sensor"
    unit_value = "mm/s"
    measured_quantity_value = PhysicalQuantity.VIBRATION
    description_value = "Measures vibration velocity"
