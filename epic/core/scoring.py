"""Built-in scoring metrics."""

from epic.core.interfaces import ScoringMetric


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


class F1Score(ScoringMetric):
    @property
    def metric_id(self) -> str:
        return "f1"

    @property
    def direction(self) -> str:
        return "maximize"

    def compute(self, y_true, y_pred) -> float:
        true_positive = sum(1 for true, pred in zip(y_true, y_pred) if true and pred)
        false_positive = sum(1 for true, pred in zip(y_true, y_pred) if not true and pred)
        false_negative = sum(1 for true, pred in zip(y_true, y_pred) if true and not pred)

        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        if precision_denominator == 0 or recall_denominator == 0:
            return 0.0

        precision = true_positive / precision_denominator
        recall = true_positive / recall_denominator
        denominator = precision + recall
        if denominator == 0.0:
            return 0.0
        return 2.0 * precision * recall / denominator

    def metadata(self) -> dict:
        return {
            "metric_id": "f1",
            "name": "F1 Score",
            "version": "1.0.0",
            "description": "Binary F1 score for anomaly detection predictions",
        }
