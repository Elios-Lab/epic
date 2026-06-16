"""Current sensor."""

from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.sensors.base import _BaseSensor


class CurrentSensor(_BaseSensor):
    sensor_id_value = "current"
    name_value = "Current Sensor"
    unit_value = "A"
    measured_quantity_value = PhysicalQuantity.CURRENT
    description_value = "Measures electrical current"
