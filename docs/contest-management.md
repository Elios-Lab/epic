# Contest Management Framework

> Related: [Domain Model](domain-model.md) — canonical entity definitions · [API Specification](api-specification.md) — REST endpoints · [Scoring](scoring.md) — metrics and leaderboards

The Contest Management Framework is responsible for creating, managing and evaluating machine learning competitions within EPIC.

A contest is the primary organizational unit of the platform.

Participants do not interact directly with digital twins.

Participants interact with contests that use one or more digital twins as problem generators.

---

# Design Goals

The contest framework must support:

- Multiple simultaneous contests
- Multiple participant groups
- Different tasks
- Different scoring policies
- Different digital twins
- Different difficulty levels
- Automatic evaluation
- Leaderboards
- Reproducible competitions

The framework must remain independent from any particular digital twin.

---

# Core Concepts

The contest system is built around the following entities:

```text
User
Contest
ContestRegistration
Task
Submission
Score
LeaderboardEntry
```

See [Domain Model](domain-model.md) for canonical entity definitions.

---

# Contest

A contest defines a machine learning challenge.

A contest contains:

- metadata
- schedule
- tasks
- scoring configuration
- allowed digital twins
- allowed scenarios
- leaderboard configuration

---

## Contest Structure

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

Tasks, allowed twins, allowed scenarios, and scoring configuration are linked entities managed separately. See [Domain Model](domain-model.md) for the full relational structure.

---

# Contest Lifecycle

Every contest follows a lifecycle.

```text
DRAFT
    ↓
SCHEDULED
    ↓
ACTIVE
    ↓
CLOSED
    ↓
ARCHIVED
```

---

## DRAFT

Contest is being configured.

Visible only to administrators.

Submissions are disabled.

---

## SCHEDULED

Contest is published.

Participants may register.

Submissions are disabled.

---

## ACTIVE

Contest is running.

The platform automatically creates and starts the contest's simulation session. The simulation runs in real wall-clock time and cannot be paused, stopped, or modified.

Participants connect via WebSocket to receive live sensor readings.

Participants may submit solutions.

Leaderboards are active.

---

## CLOSED

Contest has ended.

The simulation session is stopped. The platform sets the session status to COMPLETED.

Submissions are rejected.

Scores become final.

Participants can no longer connect to the WebSocket stream.

---

## ARCHIVED

Contest is preserved for historical purposes.

Read-only access.

---

# Contest Visibility

Supported visibility modes:

```text
PUBLIC
PRIVATE
INVITATION_ONLY
```

---

# Tasks

A contest may contain one or more tasks.

Examples:

- Forecasting
- Anomaly Detection
- Fault Classification
- Remaining Useful Life Estimation

Tasks are evaluated independently.

---

# Task Definition

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

---

# Contest Configuration

Organizers and administrators must be able to configure:

- title
- description
- dates
- rules
- tasks
- scoring policies
- visibility
- digital twins
- scenarios

---

# Contest Templates

Future versions should support reusable templates.

Examples:

- Forecasting Challenge
- Anomaly Detection Challenge
- Predictive Maintenance Challenge

---

# Users

Users interact with contests.

```python
class User:

    user_id: str

    username: str

    email: str

    password_hash: str

    role: UserRole

    is_active: bool

    created_at: datetime

    updated_at: datetime
```

See [Domain Model](domain-model.md) for the full definition.

---

# Roles

```text
ADMINISTRATOR   ← full platform management
ORGANIZER       ← creates and manages own contests
PARTICIPANT     ← registers for contests and submits predictions
```

---

# Administrator Permissions

- Full control over all contests and all users
- Everything an ORGANIZER can do, platform-wide

---

# Organizer Permissions

- Create contests
- Manage own contests through full lifecycle (DRAFT → ACTIVE → CLOSED)
- Extend deadlines on own contests
- View all submissions to own contests
- Cannot modify other organizers' contests
- Cannot manage users

---

# Participant Permissions

- Register for contests (SCHEDULED or ACTIVE)
- Connect to contest WebSocket stream and collect data client-side
- Submit predictions with temporal anchor
- View own scores and rankings

---

# Registrations

A registration links a user to a contest.

```python
class ContestRegistration:

    registration_id: str

    contest_id: str

    user_id: str

    registered_at: datetime

    status: RegistrationStatus
```

Supported statuses: `REGISTERED`, `WITHDRAWN`, `BANNED`.

The pair `(user_id, contest_id)` must be unique.

Only registered users may submit solutions.

---

# Submission System

Submissions are the primary evaluation mechanism.

A submission contains:

```python
class Submission:

    submission_id: str

    contest_id: str

    user_id: str

    task_id: str

    submitted_at: datetime              # set by the server

    prediction_from_sequence: int       # temporal integrity anchor

    payload: dict

    status: SubmissionStatus

    submission_metadata: dict | None
```

`prediction_from_sequence` is the `sequence_id` of the last observation the participant used to build their prediction. The server validates at submission time that this sequence_id was published before `submitted_at`. See [Scoring](scoring.md) for the full explanation.

Scores are stored separately as `Score` entities linked to the submission.

See [Domain Model](domain-model.md) for the full entity definition.

---

# Submission Policies

Different contests may use different policies.

Examples:

## Unlimited

Unlimited submissions.

## Daily Limit

Maximum N submissions per day.

## Best Score

Leaderboard uses best submission.

## Latest Submission

Leaderboard uses latest submission.

---

# Submission Validation

The evaluation engine must validate:

- contest state
- registration status
- submission format
- task compatibility

Invalid submissions must be rejected.

---

# Evaluation Pipeline

Every submission follows the same workflow.

```text
Submission
      ↓
Validation
      ↓
Scoring
      ↓
Storage
      ↓
Leaderboard Update
```

---

# Leaderboards

Each contest owns a leaderboard.

Leaderboards are generated automatically.

---

# Ranking Modes

## Best Score

Highest score wins.

---

## Latest Submission

Most recent valid submission wins.

---

## Multi-Metric

Several metrics are combined.

Example:

```text
Final Score =
0.7 * Forecast Score +
0.3 * Anomaly Score
```

---

# Leaderboard Entry

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

---

# Public vs Private Leaderboards

Supported modes:

```text
PUBLIC
PARTICIPANT_ONLY
ADMIN_ONLY
```

---

# Contest Resources

Each contest may provide:

- documentation
- starter code
- WebSocket client examples
- API examples
- baseline models

---

# Contest-Specific Digital Twins

A contest may restrict participants to:

```python
allowed_twins = [
    "mechanical_system"
]
```

or

```python
allowed_twins = [
    "industrial_pump",
    "electric_motor"
]
```

---

# Contest-Specific Scenarios

A contest may expose only a subset of scenarios.

Example:

```python
allowed_scenarios = [
    "normal_operation",
    "bearing_wear"
]
```

---

# Deadline Management

Organizers (for own contests) and administrators must be able to modify:

- start date
- end date

even after publication.

Typical use case:

```text
Contest deadline extension
```

without requiring contest recreation.

---

# Auditability

The system should maintain logs of:

- contest creation
- contest updates
- registrations
- submissions
- score changes

This is important for educational and research use.

---

# Future Extensions

Possible future features:

- Team-based contests
- Multi-stage competitions
- Hidden test sets
- Kaggle-style private leaderboards
- Peer-reviewed solutions
- Automatic report generation

---

# Long-Term Goal

The Contest Management Framework should allow instructors and researchers to create new competitions without writing code.

A contest should be definable primarily through configuration, while digital twins provide the underlying simulation environment.