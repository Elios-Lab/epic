"""Registration entry point for the mechanical twin plugin."""

from epic_core.scoring import MAE
from epic_twins.mechanical.faults import (
    IncreasedDampingFault,
    ReducedStiffnessFault,
    SensorBiasFault,
)
from epic_twins.mechanical.sensors import (
    AccelerationSensor,
    PositionSensor,
    TemperatureSensor,
    VelocitySensor,
)
from epic_twins.mechanical.twin import MechanicalTwin


def register():
    from epic_core.registry import (
        fault_registry,
        metric_registry,
        scenario_registry,
        sensor_registry,
        twin_registry,
    )

    twin_registry.register(MechanicalTwin())
    sensor_registry.register(PositionSensor())
    sensor_registry.register(VelocitySensor())
    sensor_registry.register(AccelerationSensor())
    sensor_registry.register(TemperatureSensor())
    fault_registry.register(IncreasedDampingFault())
    fault_registry.register(ReducedStiffnessFault())
    fault_registry.register(SensorBiasFault())
    metric_registry.register(MAE())
