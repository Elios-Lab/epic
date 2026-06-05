"""Generic plugin registry for EPIC Core."""

from __future__ import annotations

import inspect
import re
from typing import Generic, TypeVar

from epic_core.exceptions import (
    DuplicatePluginError,
    PluginNotFoundError,
    PluginValidationError,
)
from epic_core.interfaces import (
    DigitalTwin,
    ScoringMetric,
    Sensor,
)

T = TypeVar("T")

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class PluginRegistry(Generic[T]):
    def __init__(self, interface: type[T] | None = None) -> None:
        self._interface = interface
        self._plugins: dict[tuple[str, str], T] = {}

    def register(self, plugin: T) -> None:
        """
        Register a plugin instance.

        Raises PluginValidationError if the plugin fails interface validation.
        Raises DuplicatePluginError if a plugin with the same id and version
        is already registered.
        """
        plugin_id, version = self._validate(plugin)
        key = (plugin_id, version)
        if key in self._plugins:
            raise DuplicatePluginError(
                f"plugin '{plugin_id}' version '{version}' is already registered"
            )
        self._plugins[key] = plugin

    def get(self, plugin_id: str, version: str | None = None) -> T:
        """
        Retrieve a registered plugin by id.

        If version is None, returns the latest registered version.

        Raises PluginNotFoundError if no matching plugin is found.
        """
        if version is not None:
            try:
                return self._plugins[(plugin_id, version)]
            except KeyError as exc:
                raise PluginNotFoundError(
                    f"plugin '{plugin_id}' version '{version}' is not registered"
                ) from exc

        matches = [
            (registered_version, plugin)
            for (registered_id, registered_version), plugin in self._plugins.items()
            if registered_id == plugin_id
        ]
        if not matches:
            raise PluginNotFoundError(f"plugin '{plugin_id}' is not registered")
        return max(matches, key=lambda item: _semver_key(item[0]))[1]

    def list(self) -> list[T]:
        """Return all registered plugins."""
        return list(self._plugins.values())

    def contains(self, plugin_id: str) -> bool:
        return any(registered_id == plugin_id for registered_id, _ in self._plugins)

    def clear(self) -> None:
        """Remove all registered plugins."""
        self._plugins.clear()

    def _validate(self, plugin: T) -> tuple[str, str]:
        interface = self._resolve_interface(plugin)
        if interface is not None and not isinstance(plugin, interface):
            raise PluginValidationError(
                f"plugin must implement {interface.__name__}"
            )

        abstract_methods = getattr(plugin.__class__, "__abstractmethods__", frozenset())
        if inspect.isabstract(plugin.__class__) or abstract_methods:
            missing = ", ".join(sorted(abstract_methods)) or "unknown"
            raise PluginValidationError(
                f"plugin has unimplemented abstract methods: {missing}"
            )

        if not hasattr(plugin, "metadata"):
            raise PluginValidationError("plugin is missing metadata()")

        metadata = plugin.metadata()
        if not isinstance(metadata, dict):
            raise PluginValidationError("plugin metadata() must return a dict")

        id_key = _id_key_for_interface(interface, plugin)
        required_keys = {id_key, "name", "version", "description"}
        if interface is Sensor:
            required_keys.add("measured_quantity")
        missing_keys = required_keys - metadata.keys()
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise PluginValidationError(
                f"plugin metadata is missing required keys: {missing}"
            )

        plugin_id = metadata[id_key]
        version = metadata["version"]
        if not isinstance(plugin_id, str) or not plugin_id:
            raise PluginValidationError(f"plugin metadata '{id_key}' must be a string")
        if not isinstance(metadata["name"], str) or not metadata["name"]:
            raise PluginValidationError("plugin metadata 'name' must be a string")
        if not isinstance(metadata["description"], str):
            raise PluginValidationError(
                "plugin metadata 'description' must be a string"
            )
        if interface is Sensor and (
            not isinstance(metadata["measured_quantity"], str)
            or not metadata["measured_quantity"]
        ):
            raise PluginValidationError(
                "plugin metadata 'measured_quantity' must be a string"
            )
        if not isinstance(version, str) or _SEMVER_RE.fullmatch(version) is None:
            raise PluginValidationError("plugin metadata 'version' must be valid semver")

        return plugin_id, version

    def _resolve_interface(self, plugin: T) -> type | None:
        if self._interface is not None:
            return self._interface
        for interface in (DigitalTwin, Sensor, ScoringMetric):
            if isinstance(plugin, interface):
                return interface
        return None


def _id_key_for_interface(interface: type | None, plugin: object) -> str:
    interface_id_keys = {
        DigitalTwin: "twin_id",
        Sensor: "sensor_id",
        ScoringMetric: "metric_id",
    }
    if interface is not None:
        try:
            return interface_id_keys[interface]
        except KeyError as exc:
            raise PluginValidationError(
                "plugin interface could not be determined"
            ) from exc

    for attr_name, id_key in (
        ("twin_id", "twin_id"),
        ("sensor_id", "sensor_id"),
        ("metric_id", "metric_id"),
    ):
        if hasattr(plugin, attr_name):
            return id_key
    raise PluginValidationError("plugin interface could not be determined")


def _semver_key(version: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.fullmatch(version)
    if match is None:
        raise PluginValidationError("plugin metadata 'version' must be valid semver")
    return tuple(int(part) for part in match.groups())


twin_registry: PluginRegistry[DigitalTwin] = PluginRegistry(DigitalTwin)
sensor_registry: PluginRegistry[Sensor] = PluginRegistry(Sensor)
metric_registry: PluginRegistry[ScoringMetric] = PluginRegistry(ScoringMetric)
