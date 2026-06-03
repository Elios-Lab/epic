import pytest

import epic_core.registry as registry_module
from epic_core.exceptions import (
    DuplicatePluginError,
    PluginNotFoundError,
    PluginValidationError,
)
from epic_core.interfaces import ScoringMetric, Sensor
from epic_core.registry import PluginRegistry
from epic_core.testing import (
    MockFault,
    MockScenario,
    MockSensor,
    MockTwin,
    test_registry_context as registry_context,
)


class InvalidMetadataSensor(MockSensor):
    def __init__(self, metadata):
        super().__init__()
        self._metadata = metadata

    def metadata(self):
        return self._metadata


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


def test_register_and_get_plugin_by_version():
    registry = PluginRegistry(Sensor)
    sensor = MockSensor(sensor_id="temperature", version="1.0.0")

    registry.register(sensor)

    assert registry.get("temperature", "1.0.0") is sensor


def test_get_returns_latest_semver_when_version_is_omitted():
    registry = PluginRegistry(Sensor)
    older = MockSensor(sensor_id="temperature", version="1.9.0")
    newer = MockSensor(sensor_id="temperature", version="1.10.0")

    registry.register(older)
    registry.register(newer)

    assert registry.get("temperature") is newer


def test_list_returns_all_registered_plugins():
    registry = PluginRegistry(Sensor)
    sensor_a = MockSensor(sensor_id="a")
    sensor_b = MockSensor(sensor_id="b")

    registry.register(sensor_a)
    registry.register(sensor_b)

    assert set(registry.list()) == {sensor_a, sensor_b}


def test_contains_checks_plugin_id_across_versions():
    registry = PluginRegistry(Sensor)

    assert not registry.contains("temperature")
    registry.register(MockSensor(sensor_id="temperature", version="2.0.0"))

    assert registry.contains("temperature")


def test_register_rejects_duplicate_id_and_version():
    registry = PluginRegistry(Sensor)
    registry.register(MockSensor(sensor_id="temperature", version="1.0.0"))

    with pytest.raises(DuplicatePluginError):
        registry.register(MockSensor(sensor_id="temperature", version="1.0.0"))


def test_register_allows_duplicate_id_with_different_version():
    registry = PluginRegistry(Sensor)

    registry.register(MockSensor(sensor_id="temperature", version="1.0.0"))
    registry.register(MockSensor(sensor_id="temperature", version="1.1.0"))

    assert len(registry.list()) == 2


def test_get_missing_plugin_raises_plugin_not_found():
    registry = PluginRegistry(Sensor)

    with pytest.raises(PluginNotFoundError):
        registry.get("missing")


def test_get_missing_version_raises_plugin_not_found():
    registry = PluginRegistry(Sensor)
    registry.register(MockSensor(sensor_id="temperature", version="1.0.0"))

    with pytest.raises(PluginNotFoundError):
        registry.get("temperature", "2.0.0")


def test_register_rejects_object_missing_required_interface_method():
    class ConcreteMissingSensorMethod:
        @property
        def sensor_id(self):
            return "bad"

        @property
        def name(self):
            return "Bad"

        @property
        def unit(self):
            return "unit"

        def metadata(self):
            return {
                "sensor_id": "bad",
                "name": "Bad",
                "version": "1.0.0",
                "description": "Bad sensor",
            }

    registry = PluginRegistry(Sensor)

    with pytest.raises(PluginValidationError):
        registry.register(ConcreteMissingSensorMethod())


def test_register_rejects_plugin_with_unimplemented_abstract_methods():
    class ForcedAbstractSensor(MockSensor):
        pass

    sensor = ForcedAbstractSensor()
    ForcedAbstractSensor.__abstractmethods__ = frozenset({"observe"})
    registry = PluginRegistry(Sensor)

    with pytest.raises(PluginValidationError):
        registry.register(sensor)


def test_register_rejects_metadata_that_is_not_dict():
    registry = PluginRegistry(Sensor)

    with pytest.raises(PluginValidationError):
        registry.register(InvalidMetadataSensor(["not", "a", "dict"]))


def test_register_rejects_metadata_missing_required_keys():
    registry = PluginRegistry(Sensor)

    with pytest.raises(PluginValidationError):
        registry.register(InvalidMetadataSensor({"sensor_id": "sensor"}))


def test_register_rejects_invalid_semver():
    registry = PluginRegistry(Sensor)

    with pytest.raises(PluginValidationError):
        registry.register(
            InvalidMetadataSensor(
                {
                    "sensor_id": "sensor",
                    "name": "Sensor",
                    "version": "1.0",
                    "description": "Invalid version",
                }
            )
        )


def test_register_rejects_empty_plugin_id():
    registry = PluginRegistry(Sensor)

    with pytest.raises(PluginValidationError):
        registry.register(
            InvalidMetadataSensor(
                {
                    "sensor_id": "",
                    "name": "Sensor",
                    "version": "1.0.0",
                    "description": "Empty id",
                }
            )
        )


def test_register_rejects_empty_name():
    registry = PluginRegistry(Sensor)

    with pytest.raises(PluginValidationError):
        registry.register(
            InvalidMetadataSensor(
                {
                    "sensor_id": "sensor",
                    "name": "",
                    "version": "1.0.0",
                    "description": "Empty name",
                }
            )
        )


def test_register_rejects_non_string_description():
    registry = PluginRegistry(Sensor)

    with pytest.raises(PluginValidationError):
        registry.register(
            InvalidMetadataSensor(
                {
                    "sensor_id": "sensor",
                    "name": "Sensor",
                    "version": "1.0.0",
                    "description": 3,
                }
            )
        )


def test_registry_without_interface_infers_plugin_id_key():
    registry = PluginRegistry()
    sensor = MockSensor(sensor_id="sensor")

    registry.register(sensor)

    assert registry.get("sensor") is sensor


def test_registry_without_interface_infers_fault_scenario_and_metric_id_keys():
    fault_registry = PluginRegistry()
    scenario_registry = PluginRegistry()
    metric_registry = PluginRegistry()

    fault_registry.register(MockFault(fault_id="fault"))
    scenario_registry.register(MockScenario(scenario_id="scenario"))
    metric_registry.register(MockMetric())

    assert fault_registry.get("fault").fault_id == "fault"
    assert scenario_registry.get("scenario").scenario_id == "scenario"
    assert metric_registry.get("mock_metric").metric_id == "mock_metric"


def test_registry_without_interface_rejects_unknown_plugin_type():
    registry = PluginRegistry()

    with pytest.raises(PluginValidationError):
        registry.register(object())


def test_get_latest_rejects_corrupt_invalid_registered_version():
    registry = PluginRegistry(Sensor)
    registry._plugins[("sensor", "invalid")] = MockSensor(sensor_id="sensor")

    with pytest.raises(PluginValidationError):
        registry.get("sensor")


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
