"""Registration entry point for the rotating machinery twin."""

import epic.core.registry as registry_module
from epic.twins.rotating_machinery.twin import RotatingMachineryTwin


def register():
    registry_module.twin_registry.register(RotatingMachineryTwin())
