"""Registration entry point for built-in sensors."""

import epic_core.registry as registry_module
from epic_sensors.acceleration import AccelerationSensor
from epic_sensors.position import PositionSensor
from epic_sensors.temperature import TemperatureSensor
from epic_sensors.velocity import VelocitySensor


def register():
    registry_module.sensor_registry.register(PositionSensor())
    registry_module.sensor_registry.register(VelocitySensor())
    registry_module.sensor_registry.register(AccelerationSensor())
    registry_module.sensor_registry.register(TemperatureSensor())
