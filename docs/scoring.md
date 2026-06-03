# Scoring Framework

> Related: [Plugin System](plugin-system.md) — canonical `ScoringMetric` interface · [Domain Model](domain-model.md) — `Score` and `LeaderboardEntry` entities · [Contest Management](contest-management.md)

The Scoring Framework is responsible for evaluating participant submissions and generating contest rankings.

The framework must be:

- Generic
- Extensible
- Reproducible
- Independent from any specific digital twin

The EPIC Core should not contain task-specific scoring logic.

Instead, scoring is performed through reusable metrics and configurable scoring policies.

---

# Design Goals

The framework must support:

- Forecasting tasks
- Anomaly detection tasks
- Fault classification tasks
- Remaining useful life tasks
- Multi-task contests
- Multiple metrics per task
- Composite scores
- Leaderboards

The same framework should work across all domains.

---

# Fundamental Concepts

The scoring system is based on:

```text
Metric
Task
Score
Scoring Policy
Leaderboard
```

---

# Metric

A metric evaluates predictions against ground truth.

Examples:

```text
MAE
RMSE
F1 Score
Precision
Recall
ROC AUC
```

---

# Metric Interface

Every metric must implement the `ScoringMetric` abstract class defined in [Plugin System](plugin-system.md).

The interface requires implementing: `metric_id`, `direction` (`"minimize"` or `"maximize"`), `compute(y_true, y_pred)`, and `metadata()`.

---

# Score

A score represents the result of evaluating a submission.

Example:

```python
class Score:

    score_id: str

    submission_id: str

    metric_id: str

    value: float

    details: dict
```

---

# Scoring Pipeline

Every submission follows:

```text
Submission
      ↓
Validation
      ↓
Ground Truth Retrieval
      ↓
Metric Evaluation
      ↓
Score Aggregation
      ↓
Leaderboard Update
```

---

# Forecasting Tasks

Forecasting tasks require participants to predict future sensor values.

Example:

```json
{
  "forecast": {
    "horizon_1": {
      "position": 0.12
    },
    "horizon_5": {
      "position": 0.24
    }
  }
}
```

---

# Forecasting Metrics

## Mean Absolute Error (MAE)

Definition:

```text
MAE = mean(|y_true - y_pred|)
```

Properties:

- Easy to interpret
- Robust to outliers

---

## Root Mean Squared Error (RMSE)

Definition:

```text
RMSE = sqrt(mean((y_true - y_pred)^2))
```

Properties:

- Penalizes large errors

---

## Mean Absolute Percentage Error (MAPE)

Definition:

```text
MAPE = mean(|(y_true - y_pred)/y_true|)
```

Use only when denominators are well behaved.

---

## Symmetric MAPE (SMAPE)

Definition:

```text
SMAPE =
2 * |y_true - y_pred|
---------------------
|y_true| + |y_pred|
```

More robust than MAPE.

---

# Multi-Horizon Forecasting

Forecasts may contain multiple horizons.

Example:

```text
1-step
5-step
10-step
30-step
```

Scores may be computed:

- Per horizon
- Globally

---

## Example

```text
MAE@1
MAE@5
MAE@10
```

Combined score:

```text
Final Forecast Score =
0.5 * MAE@1 +
0.3 * MAE@5 +
0.2 * MAE@10
```

---

# Multi-Sensor Forecasting

Many twins expose multiple sensors.

Example:

```text
Position
Velocity
Temperature
```

Metrics should be computed:

- Per sensor
- Aggregated

Example:

```text
MAE_position
MAE_velocity
MAE_temperature
```

---

# Probabilistic Forecasting

Future versions may support uncertainty estimates.

Example:

```json
{
  "mean": 10.2,
  "std": 0.5
}
```

Potential metrics:

- CRPS
- Negative Log Likelihood
- Calibration Error

---

# Anomaly Detection Tasks

Participants estimate anomaly probabilities.

Example:

```json
{
  "anomaly_score": 0.82
}
```

---

# Binary Classification Metrics

## Accuracy

Definition:

```text
(TP + TN) / Total
```

---

## Precision

Definition:

```text
TP / (TP + FP)
```

---

## Recall

Definition:

```text
TP / (TP + FN)
```

---

## F1 Score

Definition:

```text
2 * Precision * Recall
----------------------
Precision + Recall
```

---

# Ranking Metrics

## ROC AUC

Measures ranking quality.

Useful when anomaly thresholds are unknown.

---

## PR AUC

Preferred for highly imbalanced anomaly detection tasks.

---

# Early Detection Metrics

Many industrial applications require early warnings.

A late detection may be less useful than an early one.

Future metrics may include:

```text
Detection Delay
Early Warning Score
```

---

# Fault Classification

Participants identify the fault type.

Example:

```json
{
  "fault_type": "bearing_wear"
}
```

Metrics:

- Accuracy
- Precision
- Recall
- F1
- Confusion Matrix

---

# Remaining Useful Life

Future tasks may require:

```text
Time-To-Failure Prediction
```

Metrics:

- MAE
- RMSE
- Relative Error
- Timeliness Score

---

# Composite Scores

A contest may combine multiple metrics.

Example:

```text
Forecasting Score:
70%

Anomaly Score:
30%
```

Final score:

```text
0.7 * ForecastScore +
0.3 * AnomalyScore
```

---

# Metric Direction

Some metrics are minimized.

Examples:

```text
MAE
RMSE
MAPE
```

Others are maximized.

Examples:

```text
F1
ROC AUC
PR AUC
```

The framework must store this information.

Example:

```python
direction = "maximize"
```

or

```python
direction = "minimize"
```

---

# Metric Metadata

Each metric should expose:

```python
{
    "metric_id": "mae",
    "name": "Mean Absolute Error",
    "direction": "minimize"
}
```

---

# Leaderboards

Leaderboards are generated from scores.

Supported ranking modes:

---

## Best Score

Highest performing submission wins.

---

## Latest Submission

Most recent valid submission wins.

---

## Multi-Metric

Several metrics combined.

Example:

```text
Rank Score =
0.5 * Forecast +
0.5 * Anomaly
```

---

# Public and Private Scores

Future contests may support:

## Public Score

Computed on a public validation set.

---

## Private Score

Computed on a hidden evaluation set.

This enables Kaggle-style competitions.

---

# Reproducibility

Scores must be reproducible.

Store:

- Submission
- Ground Truth Version
- Metric Version
- Contest Configuration

---

# Metric Registry

Metrics should be discoverable.

Example:

```python
metric_registry.register(MAE())

metric_registry.register(RMSE())

metric_registry.register(F1Score())
```

---

# Future Metric Library

Potential additions:

## Forecasting

- CRPS
- MASE
- Pinball Loss
- Quantile Loss

---

## Classification

- Balanced Accuracy
- Cohen's Kappa
- MCC

---

## Detection

- Detection Delay
- Time-to-Detection
- Alarm Rate

---

## Prognostics

- Timeliness Score
- NASA RUL Metrics

---

# Contest Configuration Example

```yaml
contest:
  tasks:

    forecasting:
      metrics:
        - mae
        - rmse

    anomaly_detection:
      metrics:
        - f1
        - roc_auc

  final_score:

    forecasting_weight: 0.7

    anomaly_weight: 0.3
```

---

# Design Requirement

The scoring framework must remain completely independent from:

- Digital twins
- Sensors
- Fault models
- Physical domains

A metric should operate only on predictions and ground truth.

This guarantees that new domains can be introduced without modifying the scoring system.