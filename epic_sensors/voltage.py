"""Voltage sensor."""

from epic_core.quantities import PhysicalQuantity
from epic_sensors.base import _BaseSensor


class VoltageSensor(_BaseSensor):
    sensor_id_value = "voltage"
    name_value = "Voltage Sensor"
    unit_value = "V"
    measured_quantity_value = PhysicalQuantity.VOLTAGE
    description_value = "Measures electrical voltage"
