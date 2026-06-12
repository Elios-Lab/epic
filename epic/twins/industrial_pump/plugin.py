"""Registration entry point for the industrial pump twin."""

import epic.core.registry as registry_module
from epic.twins.industrial_pump.twin import IndustrialPumpTwin


def register():
    registry_module.twin_registry.register(IndustrialPumpTwin())
