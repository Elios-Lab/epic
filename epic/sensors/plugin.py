"""Registration entry point for built-in sensors."""

import epic.core.registry as registry_module
from epic.sensors.acceleration import AccelerationSensor
from epic.sensors.co2_concentration import CO2ConcentrationSensor
from epic.sensors.current import CurrentSensor
from epic.sensors.flow_rate import FlowRateSensor
from epic.sensors.humidity import HumiditySensor
from epic.sensors.occupancy import OccupancySensor
from epic.sensors.power import PowerSensor
from epic.sensors.position import PositionSensor
from epic.sensors.pressure import PressureSensor
from epic.sensors.rotational_speed import RotationalSpeedSensor
from epic.sensors.temperature import TemperatureSensor
from epic.sensors.velocity import VelocitySensor
from epic.sensors.vibration import VibrationSensor
from epic.sensors.voltage import VoltageSensor


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
