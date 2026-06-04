"""Built-in scoring metrics."""

from epic_core.interfaces import ScoringMetric


class MAE(ScoringMetric):
    @property
    def metric_id(self) -> str:
        return "mae"

    @property
    def direction(self) -> str:
        return "minimize"

    def compute(self, y_true: list[float], y_pred: list[float]) -> float:
        """Mean Absolute Error over a flat list of values."""
        if not y_true:
            return 0.0
        return sum(abs(t - p) for t, p in zip(y_true, y_pred)) / len(y_true)

    def metadata(self) -> dict:
        return {
            "metric_id": "mae",
            "name": "Mean Absolute Error",
            "version": "1.0.0",
            "description": "Mean absolute error between predicted and true values",
        }
