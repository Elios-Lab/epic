"""Pressure sensor."""

from epic.core.quantities import PhysicalQuantity
from epic.sensors.base import _BaseSensor


class PressureSensor(_BaseSensor):
    sensor_id_value = "pressure"
    name_value = "Pressure Sensor"
    unit_value = "bar"
    measured_quantity_value = PhysicalQuantity.PRESSURE
    description_value = "Measures pressure"
