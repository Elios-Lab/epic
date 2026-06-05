"""Power sensor."""

from epic_core.quantities import PhysicalQuantity
from epic_sensors.base import _BaseSensor


class PowerSensor(_BaseSensor):
    sensor_id_value = "power"
    name_value = "Power Sensor"
    unit_value = "W"
    measured_quantity_value = PhysicalQuantity.POWER
    description_value = "Measures mechanical or electrical power"
