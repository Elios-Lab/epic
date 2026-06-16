"""Flow rate sensor."""

from epic_core.kernel.quantities import PhysicalQuantity
from epic_plugins.sensors.base import _BaseSensor


class FlowRateSensor(_BaseSensor):
    sensor_id_value = "flow_rate"
    name_value = "Flow Rate Sensor"
    unit_value = "m³/h"
    measured_quantity_value = PhysicalQuantity.FLOW_RATE
    description_value = "Measures volumetric flow rate"
