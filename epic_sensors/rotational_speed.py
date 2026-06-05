"""Rotational speed sensor."""

from epic_core.quantities import PhysicalQuantity
from epic_sensors.base import _BaseSensor


class RotationalSpeedSensor(_BaseSensor):
    sensor_id_value = "rotational_speed"
    name_value = "Rotational Speed Sensor"
    unit_value = "RPM"
    measured_quantity_value = PhysicalQuantity.ROTATIONAL_SPEED
    description_value = "Measures rotational speed"
