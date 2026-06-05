"""Registration entry point for the smart building twin."""

import epic_core.registry as registry_module
from epic_twins.smart_building.twin import SmartBuildingTwin


def register():
    registry_module.twin_registry.register(SmartBuildingTwin())
