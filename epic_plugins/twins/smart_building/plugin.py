"""Registration entry point for the smart building twin."""

import epic_core.kernel.registry as registry_module
from epic_plugins.twins.smart_building.twin import SmartBuildingTwin


def register():
    registry_module.twin_registry.register(SmartBuildingTwin())
