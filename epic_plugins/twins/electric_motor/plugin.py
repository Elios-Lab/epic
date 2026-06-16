"""Registration entry point for the electric motor twin."""

import epic_core.kernel.registry as registry_module
from epic_plugins.twins.electric_motor.twin import ElectricMotorTwin


def register():
    registry_module.twin_registry.register(ElectricMotorTwin())
