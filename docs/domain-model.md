# EPIC Domain Model

This document defines the main domain entities of EPIC and their relationships.

The domain model is designed to support:

- digital twin registration;
- simulation sessions;
- dataset generation;
- contest management;
- user registration;
- submissions;
- scoring;
- leaderboards.

The persistence layer should be independent from the simulation layer.

---

# Main Entities

EPIC is built around the following entities:

```text
User
Contest
ContestRegistration
Task
Submission
Score
LeaderboardEntry
DigitalTwinMetadata
ScenarioMetadata
SensorMetadata
SimulationSession
SensorObservation
Dataset
```

---

# User

Represents a platform user.

```python
class User:
    user_id: str
    username: str
    email: str
    password_hash: str
    role: UserRole
    created_at: datetime
    updated_at: datetime
    is_active: bool
```

Supported roles:

```text
ADMINISTRATOR
PARTICIPANT
```

Future roles:

```text
INSTRUCTOR
TEACHING_ASSISTANT
JUDGE
RESEARCHER
```

Relationships:

```text
User 1 -> N ContestRegistration
User 1 -> N Submission
```

---

# Contest

Represents a machine learning competition.

```python
class Contest:
    contest_id: str
    name: str
    description: str
    status: ContestStatus
    visibility: ContestVisibility
    start_date: datetime
    end_date: datetime
    created_by: str
    created_at: datetime
    updated_at: datetime
```

Supported statuses:

```text
DRAFT
SCHEDULED
ACTIVE
CLOSED
ARCHIVED
```

Supported visibility modes:

```text
PUBLIC
PRIVATE
INVITATION_ONLY
```

Relationships:

```text
Contest 1 -> N ContestRegistration
Contest 1 -> N Submission
Contest 1 -> N Task
Contest N -> N DigitalTwinMetadata
Contest N -> N ScenarioMetadata
```

---

# ContestRegistration

Links a user to a contest.

```python
class ContestRegistration:
    registration_id: str
    contest_id: str
    user_id: str
    registered_at: datetime
    status: RegistrationStatus
```

Supported statuses:

```text
REGISTERED
WITHDRAWN
BANNED
```

Constraints:

```text
(user_id, contest_id) must be unique
```

---

# Task

Represents one machine learning task inside a contest.

Examples:

```text
FORECASTING
ANOMALY_DETECTION
FAULT_CLASSIFICATION
REMAINING_USEFUL_LIFE
```

```python
class Task:
    task_id: str
    contest_id: str
    task_type: TaskType
    name: str
    description: str
    metric_ids: list[str]
    weight: float
    configuration: dict
```

A contest may contain multiple tasks.

Example:

```text
Final score =
0.7 * Forecasting task +
0.3 * Anomaly detection task
```

---

# Submission

Represents a participant submission.

```python
class Submission:
    submission_id: str
    contest_id: str
    user_id: str
    task_id: str
    submitted_at: datetime
    payload: dict
    status: SubmissionStatus
    metadata: dict
```

Supported statuses:

```text
PENDING
ACCEPTED
REJECTED
EVALUATED
FAILED
```

Relationships:

```text
Submission 1 -> N Score
```

---

# Score

Stores evaluation results for a submission.

```python
class Score:
    score_id: str
    submission_id: str
    metric_id: str
    value: float
    details: dict
    computed_at: datetime
```

Examples:

```text
MAE = 0.214
RMSE = 0.391
F1 = 0.82
```

---

# LeaderboardEntry

Represents a computed ranking entry.

```python
class LeaderboardEntry:
    entry_id: str
    contest_id: str
    user_id: str
    submission_id: str
    rank: int
    score: float
    updated_at: datetime
```

Leaderboards may be recomputed from submissions and scores.

Therefore, leaderboard entries can be treated as derived data.

---

# DigitalTwinMetadata

Represents metadata for a registered digital twin.

This is not the digital twin implementation itself.

The implementation lives in the plugin system.

```python
class DigitalTwinMetadata:
    twin_id: str
    name: str
    version: str
    description: str
    plugin_path: str
    metadata: dict
    is_active: bool
```

Examples:

```text
mechanical_system
industrial_pump
smart_building
```

---

# ScenarioMetadata

Represents metadata for scenarios exposed by a digital twin.

```python
class ScenarioMetadata:
    scenario_id: str
    twin_id: str
    name: str
    description: str
    difficulty_level: int
    metadata: dict
```

Examples:

```text
normal_operation
increased_damping
sensor_bias
intermittent_disturbance
```

---

# SensorMetadata

Represents metadata for sensors exposed by a digital twin.

```python
class SensorMetadata:
    sensor_id: str
    twin_id: str
    name: str
    unit: str
    sampling_rate_hz: float
    nominal_range_min: float
    nominal_range_max: float
    metadata: dict
```

The platform must not assume fixed sensor names.

---

# SimulationSession

Represents one execution of a digital twin.

```python
class SimulationSession:
    session_id: str
    user_id: str
    contest_id: str | None
    twin_id: str
    scenario_id: str
    mode: SessionMode
    status: SessionStatus
    start_time: datetime
    end_time: datetime | None
    duration_seconds: float
    sampling_rate_hz: float
    seed: int | None
    metadata: dict
```

Supported modes:

```text
TRAINING
VALIDATION
TEST
```

Supported statuses:

```text
CREATED
RUNNING
COMPLETED
FAILED
CANCELLED
```

Relationships:

```text
SimulationSession 1 -> N SensorObservation
```

---

# SensorObservation

Represents one time step of observed sensor data.

```python
class SensorObservation:
    observation_id: str
    session_id: str
    sequence_id: int
    timestamp: datetime
    sensors: dict[str, float]
    labels: dict | None
    metadata: dict
```

The `sensors` field is intentionally generic.

Example:

```json
{
  "position": 0.15,
  "velocity": 1.82,
  "temperature": 31.5
}
```

In training mode, `labels` may include:

```json
{
  "is_anomaly": false,
  "fault_type": null
}
```

In test mode, labels must not be exposed to participants.

---

# Dataset

Represents an exported dataset generated from simulations.

```python
class Dataset:
    dataset_id: str
    user_id: str
    contest_id: str | None
    twin_id: str
    scenario_ids: list[str]
    num_sessions: int
    duration_seconds: float
    sampling_rate_hz: float
    output_format: DatasetFormat
    file_path: str
    created_at: datetime
    metadata: dict
```

Supported formats:

```text
CSV
JSONL
PARQUET
```

Initially implement:

```text
CSV
JSONL
```

---

# Entity Relationships

High-level relationship model:

```text
User
 ├── ContestRegistration
 ├── Submission
 ├── SimulationSession
 └── Dataset

Contest
 ├── ContestRegistration
 ├── Task
 ├── Submission
 ├── LeaderboardEntry
 └── SimulationSession

DigitalTwinMetadata
 ├── ScenarioMetadata
 ├── SensorMetadata
 └── SimulationSession

SimulationSession
 └── SensorObservation

Submission
 └── Score
```

---

# Normalized Relational Model

Recommended database tables:

```text
users
contests
contest_registrations
tasks
submissions
scores
leaderboard_entries
digital_twins
scenarios
sensors
simulation_sessions
sensor_observations
datasets
```

For many-to-many relationships:

```text
contest_allowed_twins
contest_allowed_scenarios
```

---

# JSON Fields

Several fields are intentionally JSON-based:

```text
metadata
configuration
payload
details
sensors
labels
```

This keeps the platform extensible.

For PostgreSQL, use `JSONB`.

---

# Design Notes

The database should persist metadata and results.

The actual Python implementation of digital twins, sensors and faults should remain in the plugin system.

Do not persist executable logic in the database.

Persist only:

- identifiers;
- metadata;
- configuration;
- observations;
- submissions;
- scores.

---

# Data Visibility Rules

Training sessions may expose:

- sensor readings;
- labels;
- limited fault metadata;
- optional latent state, if explicitly enabled.

Validation sessions expose:

- sensor readings;
- possibly partial labels, depending on contest settings.

Test sessions expose:

- sensor readings only.

The persistence layer may store hidden labels for scoring, but the API must not expose them to participants.

---

# Constraints

Recommended constraints:

```text
User.email unique
User.username unique

Contest.name unique or slug unique

ContestRegistration(user_id, contest_id) unique

DigitalTwinMetadata(twin_id, version) unique

ScenarioMetadata(twin_id, scenario_id) unique

SensorMetadata(twin_id, sensor_id) unique

SimulationSession(session_id) unique

Submission(submission_id) unique
```

---

# Indexing Recommendations

Recommended indexes:

```text
users.email
users.username

contests.status
contests.start_date
contests.end_date

contest_registrations.contest_id
contest_registrations.user_id

submissions.contest_id
submissions.user_id
submissions.submitted_at

scores.submission_id

simulation_sessions.user_id
simulation_sessions.contest_id
simulation_sessions.twin_id
simulation_sessions.scenario_id

sensor_observations.session_id
sensor_observations.timestamp
sensor_observations.sequence_id

datasets.user_id
datasets.contest_id
```

---

# Reproducibility

For reproducibility, store:

- twin_id;
- twin version;
- scenario_id;
- scenario version, if available;
- seed;
- simulation configuration;
- contest configuration;
- scoring configuration.

This allows past contests and submissions to be audited and reproduced.

---

# Future Extensions

Possible future entities:

```text
Team
TeamMembership
ContestInvitation
PrivateLeaderboard
PublicLeaderboard
BaselineModel
ModelArtifact
EvaluationJob
AuditLog
Notification
```

These should not be required in the first implementation.

---

# Implementation Priority

For the first implementation, create persistence support for:

1. User
2. Contest
3. ContestRegistration
4. Task
5. Submission
6. Score
7. DigitalTwinMetadata
8. ScenarioMetadata
9. SensorMetadata
10. SimulationSession
11. SensorObservation
12. Dataset

Keep the schema simple but extensible.

The model should support future migrations without forcing a redesign.