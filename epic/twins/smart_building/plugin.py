"""Registration entry point for the smart building twin."""

import epic.core.registry as registry_module
from epic.twins.smart_building.twin import SmartBuildingTwin


def register():
    registry_module.twin_registry.register(SmartBuildingTwin())
