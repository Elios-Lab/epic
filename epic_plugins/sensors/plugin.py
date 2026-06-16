"""Registration entry point for built-in sensors."""

import epic_core.kernel.registry as registry_module
from epic_plugins.sensors.acceleration import AccelerationSensor
from epic_plugins.sensors.co2_concentration import CO2ConcentrationSensor
from epic_plugins.sensors.current import CurrentSensor
from epic_plugins.sensors.flow_rate import FlowRateSensor
from epic_plugins.sensors.humidity import HumiditySensor
from epic_plugins.sensors.occupancy import OccupancySensor
from epic_plugins.sensors.power import PowerSensor
from epic_plugins.sensors.position import PositionSensor
from epic_plugins.sensors.pressure import PressureSensor
from epic_plugins.sensors.rotational_speed import RotationalSpeedSensor
from epic_plugins.sensors.temperature import TemperatureSensor
from epic_plugins.sensors.velocity import VelocitySensor
from epic_plugins.sensors.vibration import VibrationSensor
from epic_plugins.sensors.voltage import VoltageSensor


def register():
    registry_module.sensor_registry.register(PositionSensor())
    registry_module.sensor_registry.register(VelocitySensor())
    registry_module.sensor_registry.register(AccelerationSensor())
    registry_module.sensor_registry.register(TemperatureSensor())
    registry_module.sensor_registry.register(FlowRateSensor())
    registry_module.sensor_registry.register(PressureSensor())
    registry_module.sensor_registry.register(VibrationSensor())
    registry_module.sensor_registry.register(CurrentSensor())
    registry_module.sensor_registry.register(VoltageSensor())
    registry_module.sensor_registry.register(RotationalSpeedSensor())
    registry_module.sensor_registry.register(CO2ConcentrationSensor())
    registry_module.sensor_registry.register(OccupancySensor())
    registry_module.sensor_registry.register(PowerSensor())
    registry_module.sensor_registry.register(HumiditySensor())
