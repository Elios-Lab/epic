"""Binary F1 score metric for anomaly-detection tasks."""

from epic_core.kernel.interfaces import ScoringMetric


class F1Score(ScoringMetric):
    @property
    def metric_id(self) -> str:
        return "f1"

    @property
    def direction(self) -> str:
        return "maximize"

    def compute(self, y_true, y_pred) -> float:
        true_positive = sum(1 for t, p in zip(y_true, y_pred) if t and p)
        false_positive = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
        false_negative = sum(1 for t, p in zip(y_true, y_pred) if t and not p)

        precision_denom = true_positive + false_positive
        recall_denom = true_positive + false_negative
        if precision_denom == 0 or recall_denom == 0:
            return 0.0

        precision = true_positive / precision_denom
        recall = true_positive / recall_denom
        denom = precision + recall
        if denom == 0.0:
            return 0.0
        return 2.0 * precision * recall / denom

    def metadata(self) -> dict:
        return {
            "metric_id": "f1",
            "name": "F1 Score",
            "version": "1.0.0",
            "description": "Binary F1 score for anomaly detection predictions",
        }
