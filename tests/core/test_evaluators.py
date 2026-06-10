"""Unit tests for the built-in ForecastingEvaluator."""

import pytest

from epic_core.evaluators import ForecastingEvaluator
from epic_core.exceptions import EvaluationPendingError, SubmissionError
from epic_core.scoring import F1Score, MAE


def make_observations(values: list[float], with_ground_truth: bool = True):
    return [
        {
            "sequence_id": index + 1,
            "sensors": {"position": value + 0.01},  # corrupted reading
            "ground_truth": {"position": value} if with_ground_truth else None,
            "labels": None,
        }
        for index, value in enumerate(values)
    ]


def test_metadata_and_defaults():
    evaluator = ForecastingEvaluator()
    metadata = evaluator.metadata()
    assert evaluator.task_type == "FORECASTING"
    assert evaluator.default_metric_ids == ["mae"]
    assert metadata["task_type"] == "FORECASTING"
    assert metadata["name"]
    assert metadata["version"]
    assert metadata["description"]


def test_missing_eval_steps_raises_submission_error():
    evaluator = ForecastingEvaluator()
    with pytest.raises(SubmissionError, match="eval_steps"):
        evaluator.evaluate({"forecast": {}}, {}, [], [MAE()])


def test_incomplete_window_raises_pending():
    evaluator = ForecastingEvaluator()
    observations = make_observations([0.1])
    with pytest.raises(EvaluationPendingError):
        evaluator.evaluate(
            {"forecast": {"position": [0.1, 0.2]}},
            {"eval_steps": 2},
            observations,
            [MAE()],
        )


def test_invalid_payload_raises_submission_error():
    evaluator = ForecastingEvaluator()
    observations = make_observations([0.1, 0.2])

    with pytest.raises(SubmissionError):
        evaluator.evaluate({}, {"eval_steps": 2}, observations, [MAE()])
    with pytest.raises(SubmissionError, match="exactly 2"):
        evaluator.evaluate(
            {"forecast": {"position": [0.1]}},
            {"eval_steps": 2},
            observations,
            [MAE()],
        )


def test_scores_against_ground_truth_by_default():
    evaluator = ForecastingEvaluator()
    observations = make_observations([0.1, 0.2])

    result = evaluator.evaluate(
        {"forecast": {"position": [0.1, 0.2]}},
        {"eval_steps": 2},
        observations,
        [MAE()],
    )

    assert len(result.scores) == 1
    score = result.scores[0]
    assert score.metric_id == "mae"
    assert score.value == pytest.approx(0.0)
    assert score.details["scored_against"] == "ground_truth"
    assert result.ranking_value == pytest.approx(0.0)
    assert result.ranking_direction == "minimize"


def test_falls_back_to_sensors_without_ground_truth():
    evaluator = ForecastingEvaluator()
    observations = make_observations([0.1, 0.2], with_ground_truth=False)

    result = evaluator.evaluate(
        {"forecast": {"position": [0.11, 0.21]}},
        {"eval_steps": 2},
        observations,
        [MAE()],
    )

    assert result.scores[0].details["scored_against"] == "sensors"
    assert result.scores[0].value == pytest.approx(0.0)


def test_ranking_direction_follows_primary_metric():
    evaluator = ForecastingEvaluator()
    observations = make_observations([1.0, 1.0])

    result = evaluator.evaluate(
        {"forecast": {"position": [1.0, 1.0]}},
        {"eval_steps": 2},
        observations,
        [F1Score()],
    )

    assert result.ranking_direction == "maximize"


def test_unknown_sensor_is_skipped():
    evaluator = ForecastingEvaluator()
    observations = make_observations([0.1, 0.2])

    result = evaluator.evaluate(
        {"forecast": {"nonexistent": [0.1, 0.2]}},
        {"eval_steps": 2},
        observations,
        [MAE()],
    )

    assert result.scores == []
    assert result.ranking_value is None


def test_observation_limit_follows_eval_steps():
    evaluator = ForecastingEvaluator()
    assert evaluator.observation_limit({"eval_steps": 50}) == 50
    assert evaluator.observation_limit({}) is None
