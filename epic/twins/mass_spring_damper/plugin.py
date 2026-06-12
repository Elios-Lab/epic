"""Registration entry point for the mass-spring-damper twin."""

import epic.core.registry as registry_module
from epic.twins.mass_spring_damper.twin import MassSpringDamperTwin


def register():
    registry_module.twin_registry.register(MassSpringDamperTwin())
