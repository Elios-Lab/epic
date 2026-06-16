import pytest

from epic_plugins.metrics.mae import MAE
from epic_plugins.metrics.f1 import F1Score


def test_mae_empty_lists_return_zero():
    assert MAE().compute([], []) == 0.0


def test_mae_perfect_predictions_return_zero():
    assert MAE().compute([1.0, 2.0], [1.0, 2.0]) == 0.0


def test_mae_known_single_value_error():
    assert MAE().compute([1.0], [2.0]) == 1.0


def test_mae_multiple_values_returns_mean_error():
    assert MAE().compute([1.0, 2.0, 3.0], [2.0, 2.0, 1.0]) == 1.0


def test_f1_known_case():
    assert F1Score().compute([1, 1, 1, 0], [1, 0, 1, 1]) == 2 / 3


def test_f1_perfect_predictions_return_one():
    assert F1Score().compute([True, False, True], [True, False, True]) == 1.0


def test_f1_all_wrong_predictions_return_zero():
    assert F1Score().compute([1, 1, 0, 0], [0, 0, 1, 1]) == 0.0


def test_f1_all_negative_ground_truth_returns_zero():
    assert F1Score().compute([0, 0, 0], [0, 1, 0]) == 0.0


def test_metrics_plugin_register_populates_registry():
    import epic_core.kernel.registry as registry_module
    from epic_plugins.metrics.plugin import register

    registry_module.metric_registry.clear()
    register()

    assert registry_module.metric_registry.contains("mae")
    assert registry_module.metric_registry.contains("f1")


def test_metrics_plugin_register_is_idempotent():
    from epic_core.kernel.exceptions import DuplicatePluginError
    import epic_core.kernel.registry as registry_module
    from epic_plugins.metrics.plugin import register

    registry_module.metric_registry.clear()
    register()

    with pytest.raises(DuplicatePluginError):
        register()
