"""Registration entry point for the industrial pump twin."""

import epic_core.registry as registry_module
from epic_twins.industrial_pump.twin import IndustrialPumpTwin


def register():
    registry_module.twin_registry.register(IndustrialPumpTwin())
