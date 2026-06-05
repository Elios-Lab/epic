"""Registration entry point for built-in sensors."""

import epic_core.registry as registry_module
from epic_sensors.acceleration import AccelerationSensor
from epic_sensors.current import CurrentSensor
from epic_sensors.flow_rate import FlowRateSensor
from epic_sensors.position import PositionSensor
from epic_sensors.pressure import PressureSensor
from epic_sensors.rotational_speed import RotationalSpeedSensor
from epic_sensors.temperature import TemperatureSensor
from epic_sensors.velocity import VelocitySensor
from epic_sensors.vibration import VibrationSensor
from epic_sensors.voltage import VoltageSensor


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
