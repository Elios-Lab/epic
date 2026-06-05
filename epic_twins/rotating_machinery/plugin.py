"""Registration entry point for the rotating machinery twin."""

import epic_core.registry as registry_module
from epic_twins.rotating_machinery.twin import RotatingMachineryTwin


def register():
    registry_module.twin_registry.register(RotatingMachineryTwin())
