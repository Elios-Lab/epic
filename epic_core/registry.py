"""Generic plugin registry for EPIC Core."""

from __future__ import annotations

from typing import Generic, TypeVar

from epic_core.exceptions import (
    DuplicatePluginError,
    PluginNotFoundError,
    PluginValidationError,
)
from epic_core.interfaces import DigitalTwin, ScoringMetric, Sensor, TaskEvaluator

T = TypeVar("T")


class PluginRegistry(Generic[T]):
    def __init__(
        self,
        interface: type[T],
        id_attribute: str,
    ) -> None:
        self._interface = interface
        self._id_attribute = id_attribute
        self._plugins: dict[str, T] = {}

    def register(self, plugin: T) -> None:
        """
        Register a plugin instance.

        Raises PluginValidationError if the plugin fails interface validation.
        Raises DuplicatePluginError if a plugin with the same id is already
        registered.
        """
        plugin_id = self._validate(plugin)
        if plugin_id in self._plugins:
            raise DuplicatePluginError(f"plugin '{plugin_id}' is already registered")
        self._plugins[plugin_id] = plugin

    def get(self, plugin_id: str) -> T:
        """
        Retrieve a registered plugin by id.

        Raises PluginNotFoundError if no matching plugin is found.
        """
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise PluginNotFoundError(f"plugin '{plugin_id}' is not registered") from exc

    def list(self) -> list[T]:
        """Return all registered plugins."""
        return list(self._plugins.values())

    def contains(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    def clear(self) -> None:
        """Remove all registered plugins."""
        self._plugins.clear()

    def _validate(self, plugin: T) -> str:
        if not isinstance(plugin, self._interface):
            raise PluginValidationError(
                f"plugin must implement {self._interface.__name__}"
            )

        if hasattr(plugin, "metadata"):
            metadata = plugin.metadata()
            if not isinstance(metadata, dict):
                raise PluginValidationError("plugin metadata() must return a dict")

        plugin_id = getattr(plugin, self._id_attribute)
        if not isinstance(plugin_id, str) or not plugin_id:
            raise PluginValidationError(
                f"plugin '{self._id_attribute}' must be a non-empty string"
            )
        return plugin_id


twin_registry: PluginRegistry[DigitalTwin] = PluginRegistry(DigitalTwin, "twin_id")
sensor_registry: PluginRegistry[Sensor] = PluginRegistry(Sensor, "sensor_id")
metric_registry: PluginRegistry[ScoringMetric] = PluginRegistry(
    ScoringMetric, "metric_id"
)
task_evaluator_registry: PluginRegistry[TaskEvaluator] = PluginRegistry(
    TaskEvaluator, "task_type"
)
