# EPIC Domain Model

This document defines the main domain entities of EPIC and their relationships.

The domain model is designed to support:

- digital twin registration;
- simulation sessions;
- simulation sessions;
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

Represents the single shared simulation running for a contest.

Each contest has exactly one `SimulationSession`. It is created automatically by the platform when the contest transitions to ACTIVE, and stopped when the contest transitions to CLOSED. Participants never create sessions directly.

The session runs in real wall-clock time. Its duration is `contest.end_date - contest.start_date`. It cannot be paused, stopped, or modified by participants.

```python
class SimulationSession:
    session_id: str
    contest_id: str         # FK to Contest, unique (1:1 relationship)
    twin_id: str
    scenario_id: str
    sampling_rate_hz: float
    seed: int | None
    status: SessionStatus
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    session_metadata: dict | None
```

Supported statuses:

```text
CREATED
RUNNING
COMPLETED
FAILED
```

Relationships:

```text
Contest 1 -> 1 SimulationSession
SimulationSession 1 -> N SensorObservation
```

---

# SensorObservation

Represents one time step of observed sensor data.

Observations are stored server-side for scoring purposes only. They are never exposed to participants through the API. Participants receive sensor readings exclusively through the WebSocket stream and are responsible for collecting and storing data client-side.

```python
class SensorObservation:
    observation_id: str
    session_id: str
    sequence_id: int
    timestamp: datetime
    sensors: dict[str, float]
    labels: dict | None        # stored privately for scoring; never sent to participants
    obs_metadata: dict | None
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

`labels` always contains fault ground truth:

```json
{
  "is_anomaly": true,
  "fault_ids": ["increased_damping"],
  "severities": {"increased_damping": 0.4}
}
```

This information is used by the scoring engine to evaluate submissions. It is never returned by any participant-facing API endpoint.

---

# Entity Relationships

High-level relationship model:

```text
User
 ├── ContestRegistration
 └── Submission

Contest
 ├── ContestRegistration
 ├── Task
 ├── Submission
 ├── LeaderboardEntry
 └── SimulationSession (1:1)

DigitalTwinMetadata
 ├── ScenarioMetadata
 └── SensorMetadata

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
```

For many-to-many relationships:

```text
contest_allowed_twins       (contest_id, twin_id, twin_version)
contest_allowed_scenarios   (contest_id, scenario_id, twin_id)
```

`twin_version` in `contest_allowed_twins` pins the specific plugin version the contest uses, ensuring reproducibility if a twin is updated after the contest is published. If `twin_version` is `NULL`, the latest registered version is used.

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

The simulation produces sensor readings and ground-truth labels at every time step.

Participants receive sensor readings only, through the WebSocket stream. Labels and latent state are never exposed to participants through any API endpoint.

The persistence layer stores all observations (including labels) privately for use by the scoring engine.

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

SimulationSession(contest_id) unique   ← one session per contest

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

simulation_sessions.contest_id
simulation_sessions.twin_id
simulation_sessions.status

sensor_observations.session_id
sensor_observations.timestamp
sensor_observations.sequence_id
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

Keep the schema simple but extensible.

The model should support future migrations without forcing a redesign.