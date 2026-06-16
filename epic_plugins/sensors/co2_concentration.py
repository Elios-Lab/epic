"""CO2 concentration sensor."""

from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.sensors.base import _BaseSensor


class CO2ConcentrationSensor(_BaseSensor):
    sensor_id_value = "co2_concentration"
    name_value = "CO2 Concentration Sensor"
    unit_value = "ppm"
    measured_quantity_value = PhysicalQuantity.CO2_CONCENTRATION
    description_value = "Measures indoor CO2 concentration"
