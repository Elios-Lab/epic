"""Pressure sensor."""

from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.sensors.base import _BaseSensor


class PressureSensor(_BaseSensor):
    sensor_id_value = "pressure"
    name_value = "Pressure Sensor"
    unit_value = "bar"
    measured_quantity_value = PhysicalQuantity.PRESSURE
    description_value = "Measures pressure"
