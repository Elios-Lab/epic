"""Relative humidity sensor."""

from epic.core.quantities import PhysicalQuantity
from epic.sensors.base import _BaseSensor


class HumiditySensor(_BaseSensor):
    sensor_id_value = "humidity"
    name_value = "Humidity Sensor"
    unit_value = "%RH"
    measured_quantity_value = PhysicalQuantity.HUMIDITY
    description_value = "Measures relative humidity"
