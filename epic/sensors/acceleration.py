"""Acceleration sensor."""

from epic.core.quantities import PhysicalQuantity
from epic.sensors.base import _BaseSensor


class AccelerationSensor(_BaseSensor):
    sensor_id_value = "acceleration"
    name_value = "Acceleration Sensor"
    unit_value = "m/s²"
    measured_quantity_value = PhysicalQuantity.LINEAR_ACCELERATION
    description_value = "Measures linear acceleration"
