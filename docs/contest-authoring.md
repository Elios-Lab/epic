# Contest Authoring Guide

One of the primary goals of EPIC is to allow instructors and researchers to create machine learning competitions without modifying the platform code.

Contest creation should be largely configuration-driven.

The platform should allow a contest author to create a new competition by configuring:

- A digital twin
- Sensor pipeline parameters
- A fault schedule (which faults, when, how severe)
- Initial conditions
- Tasks and scoring metrics
- Visibility and submission rules

without implementing new software components.

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


# Defining Tasks

A contest may contain one or more tasks.

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
Predict future sensor values.
```

Example:

```yaml
forecasting:

  horizons:

    - 1

    - 5

    - 10
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
forecast_horizons: [1, 5, 10]
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
forecast_horizons: [1, 5, 10]
```

---



# Contest Templates

Future versions should provide reusable templates.

Examples:

```text
Forecasting Challenge

Anomaly Detection Challenge

Predictive Maintenance Challenge

Prognostics Challenge
```

Authors should be able to instantiate a template and customize parameters.

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