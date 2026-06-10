# Contest Authoring Guide

One of the primary goals of EPIC is to allow instructors and researchers to create machine learning competitions without modifying the platform code. Contest creation is configuration-driven: an author defines a complete competition by choosing a digital twin, tuning the sensor pipeline parameters, scheduling faults (which ones, when they start and end, and how severe), setting the initial conditions, declaring the tasks with their scoring metrics, and choosing visibility and submission rules — all without implementing a single new software component. The five built-in twins available for this configuration are described in the [Digital Twin Catalog](twin-catalog.md).

---

# Contest Creation Workflow

The recommended workflow is:

```text
Select Twin
      ↓
Configure Sensors (with parameter overrides)
      ↓
Configure Fault Schedule (fault_id, start_time, end_time, severity)
      ↓
Set Initial Conditions
      ↓
Define Tasks and Metrics
      ↓
Configure Leaderboard
      ↓
Publish Contest
```

All configuration is stored directly on the contest record. There are no scenario templates — each contest explicitly defines its full simulation configuration.

---

# Contest Components

A contest consists of:

```text
Contest Metadata
Digital Twin           ← which twin to simulate
Initial Conditions     ← optional state overrides
Sensor Configs         ← which sensors, with specific parameter values
Fault Schedule         ← which faults, when they start/end, severity
Tasks and Metrics
Scoring Policy
Submission Policy
Leaderboard Policy
Visibility Rules
```

---

# Contest Metadata

Every contest should define:

```yaml
name:
description:
owner:
start_date:
end_date:
visibility:
```

Example:

```yaml
name: EPIC Forecasting Challenge 2027

description: Introductory forecasting competition

owner: ELIOS Laboratory

start_date: 2027-01-01

end_date: 2027-03-01

visibility: PUBLIC
```

---

# Selecting a Twin

A contest uses exactly one digital twin.

Example:

```yaml
twin_id: mechanical_system
```

---

# Configuring Sensors

For each sensor, the organizer specifies the sensor_id and optional parameter overrides:

```yaml
sensor_configs:
  - sensor_id: position
    noise_std: 0.005
  - sensor_id: velocity
    noise_std: 0.01
    drift_rate: 0.0005
  - sensor_id: temperature
    noise_std: 0.2
    p_outlier: 0.002
```

The platform validates that each sensor is compatible with the selected twin (its `measured_quantity` must be in `twin.supported_quantities()`).

---

# Configuring the Fault Schedule

The organizer specifies which physical faults to inject, and when:

```yaml
fault_schedule:
  - fault_id: increased_damping
    start_time: 3600.0    # seconds from simulation start
    end_time: null        # active until contest ends
    severity: 0.3         # initial severity in [0.0, 1.0]
  - fault_id: reduced_stiffness
    start_time: 7200.0
    end_time: 10800.0
    severity: 0.5
```

`fault_id` must reference a fault returned by the twin's `get_faults()`. The engine validates this at contest creation time.

# Setting Initial Conditions

Optionally override the twin's default starting state:

```yaml
initial_conditions:
  position: 0.5
  velocity: 0.0
```

Unspecified fields use the twin's defaults.

---


# Two-Phase Contest Structure

Every contest uses a **two-phase** structure that ensures submission integrity:

The contest unfolds in three consecutive windows. During the *observation phase*, from `start_date` to `end_of_observation`, the simulation runs and participants observe sensor readings via the WebSocket stream. During the *evaluation phase*, lasting `prediction_horizon_seconds` from the end of observation, the simulation continues generating ground truth but no submissions are accepted yet. Finally, the *submission window* opens when the evaluation phase ends and lasts until `end_date`; in this window participants submit their full forecast for the evaluation window.

Required fields:

```yaml
end_of_observation: 2027-01-15T12:00:00Z   # end of the observation phase
prediction_horizon_seconds: 60.0            # length of the evaluation window
```

Optional fields:

```yaml
score_against: ground_truth   # "ground_truth" (default) or "sensors"
```

`score_against` controls the reference signal used when computing the leaderboard metric. With the recommended default, `ground_truth`, scores are computed against the noiseless latent-state values recorded by the engine during the evaluation phase, so a perfect physics model achieves a score of zero and measurement noise does not penalise it. With `sensors`, scores are computed against the actual noisy sensor readings instead; choose this only when the task explicitly asks participants to forecast the corrupted measurement, as in a sensor-drift detection challenge.

The platform computes `eval_steps = round(prediction_horizon_seconds × sampling_rate_hz)`. Participants must submit exactly `eval_steps` predicted values per sensor.

Constraint: `end_date` must be after `end_of_observation + prediction_horizon_seconds` to give participants time to submit.

---

# Defining Tasks

A contest may contain one or more tasks. Each entry in the `tasks` list (or `task_type` field in the API request) causes the platform to create a `Task` entity with the corresponding `task_type` (`FORECASTING`, `ANOMALY_DETECTION`, etc.). Tasks are returned embedded in the contest response under the `tasks` key.

Example:

```yaml
tasks:

  - forecasting

  - anomaly_detection
```

---

# Forecasting Task

Goal:

```text
Predict sensor values across the full evaluation window.
```

The task configuration is computed automatically from `prediction_horizon_seconds` and `sampling_rate_hz`:

```yaml
configuration:
  prediction_horizon_seconds: 60.0
  eval_steps: 1200   # 60.0 s × 20 Hz
```

Participants submit one list of `eval_steps` values per sensor:

```json
{
  "forecast": {
    "position": [0.12, 0.13, ...],
    "velocity": [0.01, 0.02, ...]
  }
}
```

---

# Anomaly Detection Task

Goal:

```text
Detect anomalies from sensor streams.
```

Example:

```yaml
anomaly_detection:

  output:
    anomaly_score
```

---

# Fault Classification Task

Goal:

```text
Identify fault types.
```

Example:

```yaml
fault_classification:

  classes:

    - increased_damping

    - reduced_stiffness
```

---

# Remaining Useful Life Task

Future extension.

Goal:

```text
Estimate time-to-failure.
```

---

# Metric Selection

Authors choose metrics for each task.

Example:

```yaml
metrics:

  forecasting:

    - mae

    - rmse

  anomaly_detection:

    - f1

    - roc_auc
```

---

# Composite Scoring

Metrics may be combined.

Example:

```yaml
final_score:

  forecasting_weight: 0.7

  anomaly_weight: 0.3
```

Result:

```text
Final Score =
0.7 × Forecast Score
+
0.3 × Anomaly Score
```

---

# Leaderboard Configuration

The author chooses leaderboard behavior.

Supported modes:

```yaml
leaderboard:

  mode: best_score
```

or

```yaml
leaderboard:

  mode: latest_submission
```

---

# Submission Policies

Contest authors define submission limits.

Example:

```yaml
submissions:

  max_per_day: 5
```

or

```yaml
submissions:

  unlimited: true
```

---

# Registration Policies

Examples:

```yaml
registration:

  open: true
```

or

```yaml
registration:

  invitation_only: true
```

---

# Visibility Policies

Supported values:

```text
PUBLIC
PRIVATE
INVITATION_ONLY
```

Example:

```yaml
visibility: PUBLIC
```

---

# Data Visibility

Labels, fault metadata, and latent state are never exposed to participants. This is not configurable — it is a platform-level guarantee. Participants receive only sensor readings through the WebSocket stream.

---

# Contest Lifecycle Configuration

Example:

```yaml
lifecycle:

  registration_start: 2027-01-01

  contest_start: 2027-01-10

  contest_end: 2027-03-01
```

---

# Deadline Extensions

Organizers (for own contests) and administrators must be able to modify:

```yaml
contest_end
```

without recreating the contest.

This is a common real-world requirement.

---

# Example Beginner Contest

```yaml
name: Introductory Forecasting Challenge
twin_id: mass_spring_damper
sensor_configs:
  - sensor_id: position
    noise_std: 0.01
  - sensor_id: temperature
    noise_std: 0.3
fault_schedule: []
sampling_rate_hz: 10.0
task_type: FORECASTING
metric_ids: [mae]
score_against: ground_truth
start_date: 2027-01-10T09:00:00Z
end_of_observation: 2027-01-10T09:30:00Z   # 30-min observation window
prediction_horizon_seconds: 60.0           # predict the next 60 s (600 steps at 10 Hz)
end_date: 2027-01-10T10:00:00Z             # submission window closes 30 min later
visibility: PUBLIC
```

---

# Example Graduate-Level Contest

```yaml
name: Advanced Predictive Intelligence Challenge
twin_id: mass_spring_damper
sensor_configs:
  - sensor_id: position
    noise_std: 0.02
    p_outlier: 0.003
  - sensor_id: velocity
    noise_std: 0.05
  - sensor_id: temperature
    noise_std: 0.5
    drift_rate: 0.002
fault_schedule:
  - fault_id: increased_damping
    start_time: 3600.0
    end_time: null
    severity: 0.4
sampling_rate_hz: 10.0
task_type: FORECASTING
metric_ids: [mae, rmse]
score_against: ground_truth
start_date: 2027-03-01T08:00:00Z
end_of_observation: 2027-03-01T09:00:00Z   # 1-hour observation window
prediction_horizon_seconds: 300.0          # predict the next 5 min (3000 steps at 10 Hz)
end_date: 2027-03-01T12:00:00Z
visibility: PUBLIC
```

---



# Contest Templates

Predefined templates are available for all five built-in twins via the API (`GET /api/v1/templates`). A template is a complete, validated contest configuration that an organizer can retrieve and submit as-is or with parameter overrides.

Available categories:

```text
Forecasting Challenge

Anomaly Detection Challenge

Predictive Maintenance Challenge
```

To use a template, retrieve it from the API and pass it (with any overrides) to `POST /api/v1/contests`.

User-defined reusable templates — saved configurations that organizers can share — are a planned future extension.

---

# Administrative Interface

Future versions should support GUI-based contest creation with a graphical interface for selecting twins, configuring sensors, and defining the fault schedule.

without editing YAML manually.

---

# Educational Vision

Contest creation should become accessible to instructors who are not software developers.

A professor should be able to create a complete competition by configuring existing EPIC components.

The creation of a new contest should not require writing code unless a new digital twin, sensor or fault model is introduced.

This principle is one of the key long-term objectives of EPIC.