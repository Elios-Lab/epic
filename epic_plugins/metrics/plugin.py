"""Registration entry point for built-in scoring metrics."""

import epic_core.kernel.registry as registry_module
from epic_plugins.metrics.f1 import F1Score
from epic_plugins.metrics.mae import MAE


def register():
    registry_module.metric_registry.register(MAE())
    registry_module.metric_registry.register(F1Score())
