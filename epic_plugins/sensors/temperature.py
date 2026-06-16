"""Temperature sensor."""

from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.sensors.base import _BaseSensor


class TemperatureSensor(_BaseSensor):
    sensor_id_value = "temperature"
    name_value = "Temperature Sensor"
    unit_value = "°C"
    measured_quantity_value = PhysicalQuantity.TEMPERATURE
    description_value = "Measures temperature"
