# Contest Authoring Guide

One of the primary goals of EPIC is to allow instructors and researchers to create machine learning competitions without modifying the platform code.

Contest creation should be largely configuration-driven.

The platform should allow a contest author to create a new competition by selecting:

- Digital Twins
- Scenarios
- Tasks
- Metrics
- Scoring Policies
- Submission Rules
- Visibility Settings

without implementing new software components.

---

# Contest Creation Workflow

The recommended workflow is:

```text
Select Twin
      ↓
Select Scenarios
      ↓
Define Tasks
      ↓
Select Metrics
      ↓
Configure Leaderboard
      ↓
Publish Contest
```

Most contests should be creatable through configuration files or the administrative interface.

---

# Contest Components

A contest consists of:

```text
Contest Metadata
Digital Twins
Scenarios
Tasks
Metrics
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

# Selecting Digital Twins

A contest may use one or more digital twins.

Example:

```yaml
allowed_twins:

  - mechanical_system
```

or

```yaml
allowed_twins:

  - industrial_pump

  - electric_motor
```

The selected twins define the available simulation environments.

---

# Selecting Scenarios

Contest authors choose which scenarios are visible.

Example:

```yaml
allowed_scenarios:

  - normal_operation

  - increased_damping

  - sensor_bias
```

This allows gradual difficulty increases.

---

# Difficulty Levels

Contests may expose scenarios by difficulty.

Example:

```yaml
difficulty_levels:

  beginner:
    - normal_operation

  intermediate:
    - sensor_bias

  advanced:
    - multiple_faults
```

This is particularly useful for educational settings.

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

    - sensor_bias
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

# Dataset Policies

Contest authors decide what participants can access.

Example:

```yaml
datasets:

  allow_generation: true

  allow_export: true
```

---

# Label Visibility

Training contests:

```yaml
labels:

  expose_fault_labels: true
```

Research contests:

```yaml
labels:

  expose_fault_labels: false
```

---

# Latent State Visibility

Normally hidden.

Educational contests may expose it.

Example:

```yaml
latent_state:

  exposed: true
```

Useful for introductory courses.

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

Administrators must be able to modify:

```yaml
contest_end
```

without recreating the contest.

This is a common real-world requirement.

---

# Example Beginner Contest

```yaml
name: Introductory Forecasting Challenge

allowed_twins:

  - mechanical_system

allowed_scenarios:

  - normal_operation

tasks:

  - forecasting

metrics:

  forecasting:

    - mae

leaderboard:

  mode: best_score
```

---

# Example Graduate-Level Contest

```yaml
name: Advanced Predictive Intelligence Challenge

allowed_twins:

  - industrial_pump

allowed_scenarios:

  - normal_operation

  - bearing_wear

  - sensor_bias

tasks:

  - forecasting

  - anomaly_detection

metrics:

  forecasting:

    - rmse

  anomaly_detection:

    - f1

    - roc_auc

final_score:

  forecasting_weight: 0.6

  anomaly_weight: 0.4
```

---

# Example Research Contest

```yaml
name: Prognostics Benchmark

tasks:

  - forecasting

  - anomaly_detection

  - remaining_useful_life
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

Future versions should support GUI-based contest creation.

Workflow:

```text
Create Contest
      ↓
Select Twin
      ↓
Select Scenarios
      ↓
Select Tasks
      ↓
Select Metrics
      ↓
Publish
```

without editing YAML manually.

---

# Educational Vision

Contest creation should become accessible to instructors who are not software developers.

A professor should be able to create a complete competition by configuring existing EPIC components.

The creation of a new contest should not require writing code unless a new digital twin, sensor or fault model is introduced.

This principle is one of the key long-term objectives of EPIC.