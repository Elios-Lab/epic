"""Velocity sensor."""

from epic.core.quantities import PhysicalQuantity
from epic.sensors.base import _BaseSensor


class VelocitySensor(_BaseSensor):
    sensor_id_value = "velocity"
    name_value = "Velocity Sensor"
    unit_value = "m/s"
    measured_quantity_value = PhysicalQuantity.LINEAR_VELOCITY
    description_value = "Measures linear velocity"
