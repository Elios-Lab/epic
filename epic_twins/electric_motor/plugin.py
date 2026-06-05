"""Registration entry point for the electric motor twin."""

import epic_core.registry as registry_module
from epic_twins.electric_motor.twin import ElectricMotorTwin


def register():
    registry_module.twin_registry.register(ElectricMotorTwin())
