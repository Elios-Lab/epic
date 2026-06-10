# EPIC Domain Model

This document defines the main domain entities of EPIC and their relationships.

The domain model is designed to support the whole life of a competition: digital twin registration and discovery, simulation sessions, contest management, user registration, submissions, scoring, and leaderboards.

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
    first_name: str | None
    last_name: str | None
    phone_number: str | None
    password_hash: str
    role: UserRole
    status: str  # ACTIVE | SUSPENDED | DELETED
    created_at: datetime
    updated_at: datetime
```

`status` controls account access: `ACTIVE` users can log in; `SUSPENDED` users cannot but the account is preserved and can be reactivated; `DELETED` is a soft delete — the record is retained for audit purposes but login is permanently blocked. The field `is_active` is exposed in API responses as a convenience alias (`status == "ACTIVE"`).

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
User 1 -> N Invitation (as invited_by)
```

---

# OrganizerRequest

Represents a pending application for an organizer account. Submitted without authentication; reviewed by an administrator.

```python
class OrganizerRequest:
    request_id: str
    first_name: str
    last_name: str
    email: str           # unique; becomes username on approval
    phone_number: str | None
    password_hash: str
    status: str          # PENDING | APPROVED | REJECTED
    reviewed_at: datetime | None
    reviewed_by: str | None  # FK → User (administrator)
    user_id: str | None      # FK → User (created on approval)
    created_at: datetime
```

Relationships:

```text
OrganizerRequest N -> 1 User (reviewed_by, nullable)
OrganizerRequest 1 -> 1 User (user_id, created on approval, nullable)
```

---

# Invitation

Represents a competition-scoped, one-time registration token sent to a prospective participant.

```python
class Invitation:
    invitation_id: str
    email: str
    contest_id: str          # FK → Contest
    invited_by: str          # FK → User (organizer or admin)
    token: str               # unique, secrets.token_urlsafe(32)
    expires_at: datetime     # created_at + 7 days
    used: bool
    used_at: datetime | None
    user_id: str | None      # FK → User (created on acceptance)
    created_at: datetime
```

The token is delivered only by email and is never exposed in API responses. Once used or expired it cannot be reused.

Relationships:

```text
Invitation N -> 1 Contest
Invitation N -> 1 User (invited_by)
Invitation 1 -> 1 User (user_id, created on acceptance, nullable)
```

---

# Contest

Represents a machine learning competition.

```python
class Contest:
    contest_id: str
    name: str                           # unique platform-wide
    description: str
    status: ContestStatus
    visibility: ContestVisibility
    twin_id: str                        # which digital twin to simulate
    initial_conditions: dict | None     # override twin defaults (e.g. position, velocity)
    sensor_configs: list[dict]          # sensors and their parameters
    fault_schedule: list[dict]          # faults and their activation parameters
    sampling_rate_hz: float
    start_date: datetime
    end_of_observation: datetime        # observation phase ends; stream closes
    prediction_horizon_seconds: float   # length of hidden evaluation window
    end_date: datetime                  # submission window closes
    created_by: uuid                    # FK to users.id
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

A contest may contain multiple tasks. Tasks are created automatically when the contest is created; there are currently no dedicated task management endpoints (`GET/PATCH /api/v1/contests/{contest_id}/tasks`). Tasks are embedded in the contest response under the `tasks` key. See [API Specification](api-specification.md) for details.

For a forecasting task the `configuration` always includes:

```json
{
  "prediction_horizon_seconds": 60.0,
  "eval_steps": 600,
  "score_against": "ground_truth"
}
```

`eval_steps = round(prediction_horizon_seconds × sampling_rate_hz)` is computed automatically. `score_against` controls whether the MAE is measured against the clean latent state (`"ground_truth"`, default) or the noisy sensor reading (`"sensors"`).

Example multi-task score:

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
    submitted_at: datetime   # set by the server, not the client
    payload: dict            # {"forecast": {"sensor_id": [v1, v2, …]}}
    status: SubmissionStatus
    metadata: dict
```

**Temporal integrity** is enforced by the two-phase contest structure: the server only accepts submissions after `end_of_observation + prediction_horizon_seconds`, ensuring every forecast was built on data that was available before the hidden evaluation window ran. No per-submission anchor field is needed.

The `payload` for a forecasting task must contain exactly `eval_steps` values for every sensor being forecast:

```json
{
  "forecast": {
    "position": [0.12, 0.13, 0.14, …],
    "velocity": [0.01, 0.02, 0.01, …]
  }
}
```

Supported statuses:

```text
PENDING
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
CREATED     ← session record created, engine not yet started
RUNNING     ← engine active, observations being produced
PAUSED      ← organizer or admin paused the contest; engine stopped
COMPLETED   ← contest reached end_date or was closed normally
FAILED      ← unrecoverable engine error
```

On unclean server shutdown, any session left in `RUNNING` or `CREATED` state is automatically set to `PAUSED` at the next startup, allowing the organizer to resume the simulation.

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
    sensors: dict[str, float]        # noisy sensor readings — visible via WebSocket stream
    ground_truth: dict[str, float] | None  # clean latent-state values — hidden, used for scoring
    labels: dict | None              # fault metadata — hidden, never sent to participants
    obs_metadata: dict | None
```

The `sensors` field carries the realistic measurement pipeline output (noise, drift, quantisation, etc.). The `ground_truth` field carries the noiseless latent-state value for each sensor — the ideal reading before any corruption is applied. Both fields are populated by the engine during the evaluation phase.

`sensors` example (participant-visible via WebSocket):

```json
{"position": 0.153, "velocity": 1.82}
```

`ground_truth` example (server-side only, used for scoring when `score_against = "ground_truth"`):

```json
{"position": 0.148, "velocity": 1.79}
```

`labels` example (server-side only, used for anomaly-detection scoring):

```json
{
  "is_anomaly": true,
  "fault_ids": ["increased_damping"],
  "severities": {"increased_damping": 0.4}
}
```

None of `ground_truth`, `labels`, or `obs_metadata` is returned by any participant-facing API endpoint.

---

# Entity Relationships

High-level relationship model:

```text
User
 ├── ContestRegistration
 ├── Submission
 └── Invitation (as invited_by)

OrganizerRequest
 └── (approved by User → creates User)

Contest
 ├── ContestRegistration
 ├── Task
 ├── Submission
 ├── LeaderboardEntry
 ├── Invitation
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

Do not persist executable logic in the database. What the database holds is purely descriptive — identifiers, metadata, configuration, observations, submissions, and scores. The behavior those records refer to always lives in code, loaded through the plugin registries.

---

# Data Visibility Rules

The simulation produces three categories of data at every evaluation-phase time step:

| Field | Who sees it | Purpose |
|-------|-------------|---------|
| `sensors` | Participants (WebSocket stream during observation phase) | Raw material for model building |
| `ground_truth` | Server only | Clean latent-state values used by the scoring engine |
| `labels` | Server only | Fault metadata used for anomaly-detection scoring |

None of `ground_truth` or `labels` is ever returned by a participant-facing endpoint. During the observation phase the stream is open and participants receive `sensors` values. The stream closes at `end_of_observation`; from that point the evaluation window runs privately and participants cannot see any further data before submitting.

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

For reproducibility, every session must remain reconstructible from what is stored: the twin identifier and its version, the random seed, and the full simulation, contest, and scoring configurations. With these recorded, past contests and submissions can be audited and reproduced even after the platform itself has evolved.

---

# Future Extensions

Possible future entities:

```text
Team
TeamMembership
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

The first implementation provides persistence for the entities that make a competition run end to end: `User`, `Contest`, `ContestRegistration`, `Task`, `Submission`, `Score`, `LeaderboardEntry`, `SimulationSession`, and `SensorObservation`, plus the registration-workflow entities `OrganizerRequest` and `Invitation`. Digital twin metadata is not persisted — it is served live from the registry, which keeps the database free of anything that could go stale when a plugin is updated.

Keep the schema simple but extensible. The model should support future migrations without forcing a redesign.