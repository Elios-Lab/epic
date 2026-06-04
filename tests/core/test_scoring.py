from epic_core.scoring import MAE


def test_mae_empty_lists_return_zero():
    assert MAE().compute([], []) == 0.0


def test_mae_perfect_predictions_return_zero():
    assert MAE().compute([1.0, 2.0], [1.0, 2.0]) == 0.0


def test_mae_known_single_value_error():
    assert MAE().compute([1.0], [2.0]) == 1.0


def test_mae_multiple_values_returns_mean_error():
    assert MAE().compute([1.0, 2.0, 3.0], [2.0, 2.0, 1.0]) == 1.0
