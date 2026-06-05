# EPIC Domain Model

This document defines the main domain entities of EPIC and their relationships.

The domain model is designed to support:

- digital twin registration;
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
ADMINISTRATOR   ← full platform management
ORGANIZER       ← creates and manages own contests
PARTICIPANT     ← registers for contests and submits predictions
```

Future roles (Phase 4+):

```text
EXPERT          ← registers new digital twins and sensors at runtime
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
    twin_id: str                    # which digital twin to simulate
    initial_conditions: dict | None # override twin defaults (e.g. position, velocity)
    sensor_configs: list[dict]      # sensors and their parameters
    fault_schedule: list[dict]      # faults and their activation parameters
    sampling_rate_hz: float
    task_type: str                  # e.g. "FORECASTING"
    forecast_horizons: list[int]
    start_date: datetime
    end_date: datetime
    created_by: uuid                # FK to users.id
    created_at: datetime
    updated_at: datetime
```

**`sensor_configs`** — a list of sensor configurations. Each entry specifies a sensor from `sensor_registry` and overrides for its measurement pipeline parameters:

```json
[
  {"sensor_id": "position",    "noise_std": 0.005},
  {"sensor_id": "velocity",    "noise_std": 0.01, "drift_rate": 0.001},
  {"sensor_id": "temperature", "noise_std": 0.2,  "p_outlier": 0.002}
]
```

The platform validates at contest creation that each `sensor_id` is registered and that its `measured_quantity` is in `twin.supported_quantities()`.

**`fault_schedule`** — a list of fault activation entries. Each entry specifies a fault from `twin.get_faults()` and its activation timing and strength:

```json
[
  {
    "fault_id":   "increased_damping",
    "start_time": 3600.0,
    "end_time":   null,
    "severity":   0.3
  }
]
```

`start_time` and `end_time` are in seconds from the simulation start (0 = contest start). `severity` is in [0.0, 1.0]. `end_time = null` means the fault is active until the contest ends.

**`initial_conditions`** — optional dict of state variable overrides passed to `twin.configure()`. Keys match the twin's state field names. Unspecified fields use the twin's defaults.

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
    submitted_at: datetime          # set by the server, not the client
    prediction_from_sequence: int   # sequence_id of the last observation
                                    # the participant used to build this prediction
    payload: dict
    status: SubmissionStatus
    metadata: dict
```

`prediction_from_sequence` is the `sequence_id` of the most recent observation the participant claims to have used when producing their prediction. The server validates at submission time that this sequence_id was actually published at or before `submitted_at` — i.e., the participant cannot anchor their prediction from a future observation they could not yet have received.

This is the primary mechanism EPIC uses to guarantee **temporal honesty**: predictions must be genuinely prospective. See [Scoring](scoring.md) for how this anchor is used during evaluation.

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

Represents metadata for a registered digital twin. Returned by `GET /api/v1/twins` and related endpoints.

```python
class DigitalTwinMetadata:
    twin_id: str
    name: str
    version: str
    description: str
    metadata: dict
```

Examples:

```text
mechanical_system
industrial_pump
smart_building
```

---

# SensorMetadata

Represents metadata for sensors exposed by a digital twin.

```python
class SensorMetadata:
    sensor_id: str
    name: str
    unit: str
    measured_quantity: str    # PhysicalQuantity.value
    version: str
    description: str
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
simulation_sessions
sensor_observations
```

For many-to-many relationships:

```text
contest_allowed_twins       (contest_id, twin_id, twin_version)
```

`twin_version` in `contest_allowed_twins` pins the specific twin version the contest uses, ensuring reproducibility if a twin is updated after the contest is published. If `twin_version` is `NULL`, the latest registered version is used.

**Phase 3 note:** the `contest_allowed_twins` junction table is not yet implemented. Each Contest record directly stores `twin_id`. Multi-twin contests and version pinning are deferred to a future phase.

---

# JSON Fields

Several fields are intentionally JSON-based:

```text
metadata
configuration
payload
details
labels
```

This keeps the platform extensible.

For PostgreSQL, use `JSONB`.

---

# Design Notes

The database should persist metadata and results.

The actual Python implementation of digital twins, sensors and faults lives in `epic_twins/` and `epic_sensors/`.

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


SensorMetadata(sensor_id) unique

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
8. SimulationSession
11. SensorObservation

Keep the schema simple but extensible.

The model should support future migrations without forcing a redesign.