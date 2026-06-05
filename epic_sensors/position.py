"""Position sensor."""

from epic_core.quantities import PhysicalQuantity
from epic_sensors.base import _BaseSensor


class PositionSensor(_BaseSensor):
    sensor_id_value = "position"
    name_value = "Position Sensor"
    unit_value = "m"
    measured_quantity_value = PhysicalQuantity.LINEAR_POSITION
    description_value = "Measures linear position"
