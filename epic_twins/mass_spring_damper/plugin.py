"""Registration entry point for the mass-spring-damper twin."""

import epic_core.registry as registry_module
from epic_twins.mass_spring_damper.twin import MassSpringDamperTwin


def register():
    registry_module.twin_registry.register(MassSpringDamperTwin())
