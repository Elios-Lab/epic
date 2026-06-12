"""Registration entry point for the electric motor twin."""

import epic.core.registry as registry_module
from epic.twins.electric_motor.twin import ElectricMotorTwin


def register():
    registry_module.twin_registry.register(ElectricMotorTwin())
