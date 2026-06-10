"""Built-in task evaluators."""

from __future__ import annotations

from epic_core.exceptions import EvaluationPendingError, SubmissionError
from epic_core.interfaces import (
    EvaluationResult,
    MetricScore,
    ScoringMetric,
    TaskEvaluator,
)


class ForecastingEvaluator(TaskEvaluator):
    """
    Scores two-phase forecasting submissions against the recorded
    evaluation-window observations.

    The payload must contain {"forecast": {sensor_id: [v1, ..., v_eval_steps]}}.
    Scoring uses the reference signal selected by the task configuration's
    "score_against" field ("ground_truth" by default, falling back to
    "sensors" when ground truth was not recorded).

    The leaderboard ranking value is the mean of the primary metric (the
    first configured metric) across all forecast sensors, ranked according
    to that metric's declared direction.
    """

    def __init__(self, version: str = "1.0.0") -> None:
        self._version = version

    @property
    def task_type(self) -> str:
        return "FORECASTING"

    @property
    def default_metric_ids(self) -> list[str]:
        return ["mae"]

    def observation_limit(self, configuration: dict) -> int | None:
        eval_steps = configuration.get("eval_steps")
        return int(eval_steps) if eval_steps else None

    def evaluate(
        self,
        payload: dict,
        configuration: dict,
        observations: list[dict],
        metrics: list[ScoringMetric],
    ) -> EvaluationResult:
        eval_steps = configuration.get("eval_steps")
        if not eval_steps:
            raise SubmissionError("Task configuration missing eval_steps")

        if len(observations) < eval_steps:
            raise EvaluationPendingError(
                "Evaluation window not yet complete — scoring deferred"
            )
        observations = observations[:eval_steps]

        forecast = self._parse_forecast(payload, eval_steps)
        sensor_ids = list(forecast.keys())

        # "ground_truth" uses the noiseless latent-state values stored by the
        # engine; "sensors" uses the corrupted readings. If ground truth was
        # not recorded, fall back to sensors automatically.
        score_against = configuration.get("score_against", "ground_truth")
        use_ground_truth = (
            score_against == "ground_truth"
            and observations[0].get("ground_truth") is not None
        )
        reference_key = "ground_truth" if use_ground_truth else "sensors"
        reference = observations[0].get(reference_key) or {}

        scores: list[MetricScore] = []
        per_metric_values: dict[str, list[float]] = {}
        for metric in metrics:
            for sensor_id in sensor_ids:
                if sensor_id not in reference:
                    continue
                y_true = [
                    float((obs.get(reference_key) or {})[sensor_id])
                    for obs in observations
                ]
                y_pred = [float(value) for value in forecast[sensor_id]]
                value = metric.compute(y_true, y_pred)
                scores.append(MetricScore(
                    metric_id=metric.metric_id,
                    value=value,
                    details={
                        "sensor_id": sensor_id,
                        "eval_steps": eval_steps,
                        "scored_against": reference_key,
                    },
                ))
                per_metric_values.setdefault(metric.metric_id, []).append(value)

        # Leaderboard ranking: mean of the primary metric across sensors,
        # honouring its declared direction.
        ranking_value = None
        ranking_direction = "minimize"
        if metrics:
            primary = metrics[0]
            values = per_metric_values.get(primary.metric_id)
            if values:
                ranking_value = sum(values) / len(values)
                ranking_direction = primary.direction

        return EvaluationResult(
            scores=scores,
            ranking_value=ranking_value,
            ranking_direction=ranking_direction,
        )

    def _parse_forecast(self, payload: dict, eval_steps: int) -> dict:
        try:
            forecast = payload["forecast"]
            if not isinstance(forecast, dict):
                raise TypeError(
                    "payload.forecast must be a dict of {sensor_id: [values]}"
                )
            for sensor_id, values in forecast.items():
                if not isinstance(values, list) or len(values) != eval_steps:
                    raise ValueError(
                        f"sensor '{sensor_id}' must have exactly {eval_steps} "
                        f"predicted values, got "
                        f"{len(values) if isinstance(values, list) else type(values).__name__}"
                    )
        except (KeyError, TypeError, ValueError) as exc:
            raise SubmissionError(str(exc)) from exc
        return forecast

    def metadata(self) -> dict:
        return {
            "task_type": self.task_type,
            "name": "Time-Series Forecasting",
            "version": self._version,
            "description": (
                "Scores forecasts of the evaluation window against recorded "
                "ground truth or sensor readings"
            ),
        }
