"""Occupancy sensor."""

from epic_core.quantities import PhysicalQuantity
from epic_sensors.base import _BaseSensor


class OccupancySensor(_BaseSensor):
    sensor_id_value = "occupancy"
    name_value = "Occupancy Sensor"
    unit_value = "people"
    measured_quantity_value = PhysicalQuantity.OCCUPANCY
    description_value = "Measures occupant count"
