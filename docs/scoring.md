# Scoring Framework

The Scoring Framework is responsible for evaluating participant submissions and generating contest rankings. It must be generic, extensible, reproducible, and independent from any specific digital twin: the EPIC Core does not contain task-specific scoring logic, and evaluation is performed through reusable metrics combined by configurable scoring policies. A metric operates only on predictions and ground truth — it never sees a twin, a sensor, or a physical domain — which is what guarantees that new domains can be introduced without modifying the scoring system.

The framework is designed to eventually cover forecasting, anomaly detection, fault classification, and remaining-useful-life tasks, including multi-task contests with multiple metrics per task and composite scores. Forecasting is the task type implemented today; the others are roadmap items whose requirements shaped the design, and each will arrive as a `TaskEvaluator` plugin rather than as a platform change.

---

# Fundamental Concepts

Five concepts structure the system. A **metric** evaluates predictions against ground truth and is the smallest reusable unit — MAE, RMSE, and F1 are metrics. A **task** declares what participants must produce and which metrics evaluate it. A **score** is the stored result of applying one metric to one submission. A **task evaluator** is the scoring policy for a task type: it validates the payload, applies the configured metrics, and decides how the resulting scores combine into a single ranking value. A **leaderboard** orders participants by that value.

Task evaluators are plugins, exactly like twins, sensors, and metrics. Each one implements the `TaskEvaluator` interface from `epic_core/interfaces.py` — a `task_type` identifier, a pure `evaluate(payload, configuration, observations, metrics)` function returning an `EvaluationResult`, and `metadata()` — and is registered in the `task_evaluator_registry` at startup. The API layer dispatches every submission to the evaluator registered for its task type and accepts any task type with a registered evaluator at contest creation, so adding a new contest type (anomaly detection, fault classification, RUL) means writing one evaluator class and registering it: no EPIC Core or API change. The built-in `ForecastingEvaluator` lives in `epic_core/evaluators.py` and is the reference implementation. An evaluator never touches the database or the registries — the caller hands it the recorded observations as plain data — which keeps scoring reproducible and trivially unit-testable.

Every metric implements the `ScoringMetric` abstract class defined in `epic_core/interfaces.py`, which requires a `metric_id`, a `direction` (`"minimize"` or `"maximize"`), a `compute(y_true, y_pred)` method, and a `metadata()` method. The direction matters: MAE, RMSE, and MAPE are minimized, while F1, ROC AUC, and PR AUC are maximized, and the leaderboard logic must consult the declared direction rather than assume one. Metrics are registered in the `metric_registry` at startup and referenced from task configuration by their identifier, so adding a metric is a pure plugin operation.

Each evaluation produces a `Score` record linking the submission to the metric, carrying the numeric value and a `details` dictionary with the evaluation context (which sensor, how many steps, which reference signal was used).

---

# The Scoring Pipeline

Every submission follows the same path: a temporal integrity check (is the submission window open?), payload validation, ground truth retrieval, metric evaluation, score storage, and a leaderboard update. The steps after validation run asynchronously — the participant receives an immediate response with the submission in `PENDING` status, and the status moves to `EVALUATED` or `FAILED` when scoring completes.

---

# Submission Integrity: The Two-Phase Structure

EPIC competitions run on a shared real-time simulation, and that creates a specific cheating opportunity: since all participants receive the same sensor readings, a dishonest participant could simply watch the data they are supposed to forecast and submit "predictions" computed after the fact.

The two-phase contest structure eliminates this possibility by construction. During the *observation phase*, from `start_date` to `end_of_observation`, the simulation runs and participants observe sensor readings through the WebSocket stream — this is the data they train on. During the *evaluation phase*, lasting `prediction_horizon_seconds` from the end of observation, the simulation keeps producing ground truth, but the stream is closed and no submissions are accepted yet. Only after the evaluation window has fully elapsed does the server begin accepting submissions. At that point every participant is forecasting the same window, and none of them can have seen it: every accepted submission is genuinely prospective, built only from observation-phase data.

The size of the forecast is fixed by the contest configuration:

```text
eval_steps = round(prediction_horizon_seconds × sampling_rate_hz)
```

A forecasting task also declares `target_variables`, the one or more configured sensor ids the organizer requires participants to predict. Scoring is computed only for those targets. A forecasting payload must contain exactly one list of `eval_steps` predicted values per required target variable:

```json
{
  "forecast": {
    "position": [0.12, 0.13, 0.14, ...],
    "velocity": [0.01, 0.02, 0.01, ...]
  }
}
```

Payloads with missing target variables, wrong list lengths, or non-numeric values fail validation and the submission is marked `FAILED` with the reason recorded in its metadata. Extra forecast keys are ignored for scoring. If scoring runs before the evaluation window is fully populated with ground-truth observations, the submission is left in `PENDING` and scoring is retried once enough observations exist.

---

# Ground Truth vs. Sensor Readings

Every sensor applies a configurable measurement pipeline — noise, drift, quantization, outlier injection — before producing a reading, as described in [Sensors](sensors.md). Scoring against those corrupted readings would penalize a perfect physical model for measurement errors it cannot possibly predict. For this reason EPIC stores two reference signals for every evaluation-phase observation: the `sensors` field holds the corrupted reading, which is what participants would have seen, and the `ground_truth` field holds the clean latent-state value taken from the digital twin before any sensor corruption, which participants never see.

The organizer chooses the scoring reference through the `score_against` task configuration field. The default, `"ground_truth"`, makes scores reflect genuine model quality rather than luck with the noise. The alternative, `"sensors"`, is appropriate when forecasting the raw measurement is itself the point — for example when sensor drift is the phenomenon participants are asked to model. Whichever reference is used is recorded in the `scored_against` key of each score's `details`, so results remain interpretable after the fact.

---

# Forecasting Metrics

The implemented forecasting metric is the mean absolute error, `MAE = mean(|y_true − y_pred|)`, computed per configured target variable over the full evaluation window. It is easy to interpret (it is expressed in the target sensor's own unit) and robust to occasional large errors.

The metric library is expected to grow along well-known lines. RMSE, `sqrt(mean((y_true − y_pred)²))`, penalizes large errors more heavily than MAE. MAPE expresses errors as percentages but misbehaves when true values approach zero, so it should only be configured when denominators are well behaved; SMAPE, which normalizes by the sum of the absolute true and predicted values, is the more robust variant. Further out, multi-horizon scoring (separate scores at one, five, and ten steps combined with configured weights) and probabilistic forecasting metrics such as CRPS, negative log likelihood, and calibration error are anticipated — the latter requiring participants to submit uncertainty estimates alongside point forecasts.

When a contest configures multiple target variables, metrics are computed per target and the per-target values are then aggregated by the scoring policy. Non-target sensors can still be streamed to participants as explanatory inputs, but they do not affect the score unless the organizer includes them in `target_variables`. This keeps the individual scores interpretable (a position MAE in meters, a temperature MAE in degrees) while still producing a single ranking value.

---

# Classification and Detection Metrics

For anomaly detection and fault classification tasks, the framework already includes a binary F1 score, the harmonic mean of precision and recall. The expected library extensions are the standard ones — accuracy, precision, recall, ROC AUC for threshold-free ranking quality, and PR AUC for the highly imbalanced label distributions typical of anomaly detection. Industrial detection tasks also care about *when* a fault is detected, not only whether: detection-delay and early-warning metrics, which reward catching a developing fault before it becomes obvious, are planned for the same roadmap phase as the anomaly detection task type. Fault classification will additionally report per-class metrics and confusion matrices, and remaining-useful-life estimation will reuse the regression metrics together with prognostics-specific timeliness scores that penalize late predictions more than early ones.

---

# Composite Scores and Leaderboards

A contest that evaluates several metrics — or several tasks — needs a rule for combining them into one ranking value. That rule belongs to the task evaluator, which returns alongside its scores a single `ranking_value` and the `ranking_direction` to interpret it. The built-in forecasting evaluator ranks by the primary metric (the first configured one) averaged across the configured target variables, in that metric's declared direction; richer policies — weighted combinations such as seventy percent forecasting and thirty percent anomaly score, with normalization across directions — are the natural evolution of the same hook and require no platform change.

Leaderboards are generated from scores automatically and honour the ranking direction: with a minimized metric like MAE the lowest value ranks first and a participant's lowest submission is kept as their best, while with a maximized metric like F1 the ordering and the best-score rule invert. Latest-submission ranking and public/private leaderboard splits, where the public standing is computed on part of the evaluation window and the final standing on the rest, are planned extensions that enable Kaggle-style competition formats.

---

# Reproducibility

Scores must be reproducible after the fact. The platform stores everything needed to re-derive any score: the submission payload itself, the ground truth it was evaluated against, the metric identifier and version, and the contest configuration. Re-running the metric over the stored inputs must produce the stored value — this property is what makes the platform usable for research benchmarking, and it is a fixed design requirement for any future metric or policy.
