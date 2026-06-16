import pytest

import epic_core.kernel.registry as registry_module
from epic_core.kernel.exceptions import (
    DuplicatePluginError,
    PluginNotFoundError,
    PluginValidationError,
)
from epic_core.kernel.interfaces import ScoringMetric, Sensor
from epic_core.kernel.registry import PluginRegistry
from epic_core.kernel.testing import (
    MockSensor,
    MockTwin,
    test_registry_context as registry_context,
)


class InvalidMetadataSensor(MockSensor):
    def metadata(self):
        return ["not", "a", "dict"]


class EmptyIdSensor(MockSensor):
    @property
    def sensor_id(self) -> str:
        return ""


class MockMetric(ScoringMetric):
    @property
    def metric_id(self) -> str:
        return "mock_metric"

    @property
    def direction(self) -> str:
        return "minimize"

    def compute(self, y_true, y_pred) -> float:
        return 0.0

    def metadata(self) -> dict:
        return {
            "metric_id": self.metric_id,
            "name": "Mock Metric",
            "version": "1.0.0",
            "description": "Mock metric for registry tests",
        }


def test_register_and_get_plugin():
    registry = PluginRegistry(Sensor, "sensor_id")
    sensor = MockSensor(sensor_id="temperature", version="1.0.0")

    registry.register(sensor)

    assert registry.get("temperature") is sensor


def test_list_returns_all_registered_plugins():
    registry = PluginRegistry(Sensor, "sensor_id")
    sensor_a = MockSensor(sensor_id="a")
    sensor_b = MockSensor(sensor_id="b")

    registry.register(sensor_a)
    registry.register(sensor_b)

    assert set(registry.list()) == {sensor_a, sensor_b}


def test_contains_checks_plugin_id():
    registry = PluginRegistry(Sensor, "sensor_id")

    assert not registry.contains("temperature")
    registry.register(MockSensor(sensor_id="temperature", version="2.0.0"))

    assert registry.contains("temperature")


def test_clear_removes_registered_plugins():
    registry = PluginRegistry(Sensor, "sensor_id")
    registry.register(MockSensor(sensor_id="temperature"))

    registry.clear()

    assert registry.list() == []
    assert not registry.contains("temperature")


def test_register_rejects_duplicate_id():
    registry = PluginRegistry(Sensor, "sensor_id")
    registry.register(MockSensor(sensor_id="temperature", version="1.0.0"))

    with pytest.raises(DuplicatePluginError):
        registry.register(MockSensor(sensor_id="temperature", version="1.1.0"))


def test_get_missing_plugin_raises_plugin_not_found():
    registry = PluginRegistry(Sensor, "sensor_id")

    with pytest.raises(PluginNotFoundError):
        registry.get("missing")


def test_register_rejects_object_missing_required_interface():
    registry = PluginRegistry(Sensor, "sensor_id")

    with pytest.raises(PluginValidationError):
        registry.register(object())


def test_register_rejects_metadata_that_is_not_dict():
    registry = PluginRegistry(Sensor, "sensor_id")

    with pytest.raises(PluginValidationError):
        registry.register(InvalidMetadataSensor())


def test_register_rejects_empty_plugin_id():
    registry = PluginRegistry(Sensor, "sensor_id")

    with pytest.raises(PluginValidationError):
        registry.register(EmptyIdSensor())


def test_registry_uses_explicit_metric_id_attribute():
    registry = PluginRegistry(ScoringMetric, "metric_id")
    metric = MockMetric()

    registry.register(metric)

    assert registry.get("mock_metric") is metric


def test_test_registry_context_installs_and_restores_registries():
    original_twin_registry = registry_module.twin_registry

    with registry_context(twins=[MockTwin(twin_id="test_twin")]) as registries:
        assert registry_module.twin_registry is registries.twin
        assert registries.twin.get("test_twin").twin_id == "test_twin"

    assert registry_module.twin_registry is original_twin_registry


def test_test_registry_context_restores_on_exception():
    original = registry_module.twin_registry
    with pytest.raises(RuntimeError):
        with registry_context(twins=[MockTwin()]):
            raise RuntimeError("boom")
    assert registry_module.twin_registry is original
