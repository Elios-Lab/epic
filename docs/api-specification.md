# API Specification

This document defines the REST and WebSocket APIs exposed by EPIC.

The API provides access to:

- Authentication
- Users
- Contests
- Contest Registrations
- Tasks
- Digital Twins
- Scenarios
- Sensors
- Simulation Sessions
- Observations
- Datasets
- Submissions
- Scores
- Leaderboards

The API follows REST principles and uses JSON payloads.

The API must remain independent from:

- Digital Twin implementations
- Sensor implementations
- Fault models
- Physical domains

---

# API Versioning

All endpoints must be versioned.

Current version:

```text
/api/v1
```

Example:

```http
GET /api/v1/contests
```

Future versions should coexist whenever possible.

---

# Authentication

## Login

```http
POST /api/v1/auth/login
```

Request:

```json
{
  "username": "student1",
  "password": "********"
}
```

Response:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## Refresh Token

```http
POST /api/v1/auth/refresh
```

---

## Current User

```http
GET /api/v1/auth/me
```

---

# Users

## List Users

```http
GET /api/v1/users
```

Administrator only.

---

## Create User

```http
POST /api/v1/users
```

---

## Get User

```http
GET /api/v1/users/{user_id}
```

---

## Update User

```http
PATCH /api/v1/users/{user_id}
```

---

## Delete User

```http
DELETE /api/v1/users/{user_id}
```

---

# Contests

A contest is a first-class resource.

Contest lifecycle transitions are managed through updates.

---

## List Contests

```http
GET /api/v1/contests
```

Query parameters:

```text
status
visibility
limit
offset
```

---

## Create Contest

```http
POST /api/v1/contests
```

Administrator only.

---

## Get Contest

```http
GET /api/v1/contests/{contest_id}
```

---

## Update Contest

```http
PATCH /api/v1/contests/{contest_id}
```

Administrator only.

Typical updates:

```json
{
  "end_date": "2027-03-15T23:59:59Z"
}
```

or

```json
{
  "status": "ACTIVE"
}
```

or

```json
{
  "status": "CLOSED"
}
```

---

## Delete Contest

```http
DELETE /api/v1/contests/{contest_id}
```

Administrator only.

---

# Contest Lifecycle

Supported values:

```text
DRAFT
SCHEDULED
ACTIVE
CLOSED
ARCHIVED
```

State transitions are performed using:

```http
PATCH /api/v1/contests/{contest_id}
```

Example:

```json
{
  "status": "SCHEDULED"
}
```

The server validates allowed transitions.

---

# Contest Tasks

Tasks belong to contests.

---

## List Contest Tasks

```http
GET /api/v1/contests/{contest_id}/tasks
```

---

## Create Contest Task

```http
POST /api/v1/contests/{contest_id}/tasks
```

Administrator only.

---

## Get Contest Task

```http
GET /api/v1/contests/{contest_id}/tasks/{task_id}
```

---

## Update Contest Task

```http
PATCH /api/v1/contests/{contest_id}/tasks/{task_id}
```

---

## Delete Contest Task

```http
DELETE /api/v1/contests/{contest_id}/tasks/{task_id}
```

---

# Contest Registrations

Contest registrations are resources.

Participants register by creating a registration.

---

## List Registrations

```http
GET /api/v1/contest-registrations
```

Administrator only.

Filters:

```text
contest_id
user_id
```

---

## Create Registration

```http
POST /api/v1/contest-registrations
```

Request:

```json
{
  "contest_id": "forecast_2027"
}
```

The user is inferred from the JWT token.

---

## Get Registration

```http
GET /api/v1/contest-registrations/{registration_id}
```

---

## Delete Registration

```http
DELETE /api/v1/contest-registrations/{registration_id}
```

Represents withdrawal from a contest.

---

# Leaderboards

Leaderboards are derived resources.

---

## Get Contest Leaderboard

```http
GET /api/v1/contests/{contest_id}/leaderboard
```

---

## Get User Ranking

```http
GET /api/v1/contests/{contest_id}/leaderboard/{user_id}
```

---

# Digital Twins

Digital twins are exposed as metadata resources.

---

## List Twins

```http
GET /api/v1/twins
```

---

## Get Twin

```http
GET /api/v1/twins/{twin_id}
```

---

# Scenarios

Scenarios belong to digital twins.

---

## List Twin Scenarios

```http
GET /api/v1/twins/{twin_id}/scenarios
```

---

## Get Scenario

```http
GET /api/v1/twins/{twin_id}/scenarios/{scenario_id}
```

---

# Sensors

Sensors belong to digital twins.

---

## List Twin Sensors

```http
GET /api/v1/twins/{twin_id}/sensors
```

---

## Get Sensor

```http
GET /api/v1/twins/{twin_id}/sensors/{sensor_id}
```

---

# Simulation Sessions

A session represents one execution of a digital twin.

---

## List Sessions

```http
GET /api/v1/sessions
```

Filters:

```text
user_id
contest_id
twin_id
scenario_id
status
```

---

## Create Session

```http
POST /api/v1/sessions
```

Example:

```json
{
  "twin_id": "mechanical_system",
  "scenario_id": "normal_operation",
  "mode": "TRAINING",
  "duration_seconds": 600,
  "sampling_rate_hz": 10
}
```

---

## Get Session

```http
GET /api/v1/sessions/{session_id}
```

---

## Update Session

```http
PATCH /api/v1/sessions/{session_id}
```

---

## Delete Session

```http
DELETE /api/v1/sessions/{session_id}
```

---

# Observations

Observations belong to sessions.

---

## List Observations

```http
GET /api/v1/sessions/{session_id}/observations
```

Parameters:

```text
offset
limit
from_timestamp
to_timestamp
```

---

## Get Observation

```http
GET /api/v1/sessions/{session_id}/observations/{observation_id}
```

---

# Datasets

Datasets are resources generated from simulation sessions.

---

## List Datasets

```http
GET /api/v1/datasets
```

---

## Create Dataset

```http
POST /api/v1/datasets
```

Example:

```json
{
  "twin_id": "mechanical_system",
  "scenario_ids": [
    "normal_operation",
    "sensor_bias"
  ],
  "num_sessions": 50,
  "duration_seconds": 600,
  "sampling_rate_hz": 10,
  "output_format": "CSV"
}
```

---

## Get Dataset

```http
GET /api/v1/datasets/{dataset_id}
```

---

## Download Dataset

```http
GET /api/v1/datasets/{dataset_id}/download
```

---

## Delete Dataset

```http
DELETE /api/v1/datasets/{dataset_id}
```

---

# Submissions

Submissions are contest resources.

---

## List Submissions

```http
GET /api/v1/contests/{contest_id}/submissions
```

---

## Create Submission

```http
POST /api/v1/contests/{contest_id}/submissions
```

---

## Get Submission

```http
GET /api/v1/submissions/{submission_id}
```

---

## Delete Submission

```http
DELETE /api/v1/submissions/{submission_id}
```

If contest rules allow it.

---

# Scores

Scores are derived resources generated from submissions.

---

## Get Submission Scores

```http
GET /api/v1/submissions/{submission_id}/scores
```

---

## Get Contest Scores

```http
GET /api/v1/contests/{contest_id}/scores
```

Administrator only.

---

# WebSocket API

EPIC provides real-time sensor streaming.

---

## Session Stream

```text
WS /api/v1/ws/sessions/{session_id}
```

Message:

```json
{
  "timestamp": "2027-01-01T12:00:00Z",
  "session_id": "abc123",
  "sequence_id": 100,
  "sensors": {
    "position": 0.15,
    "velocity": 1.82,
    "temperature": 31.5
  }
}
```

The sensor dictionary is generated dynamically by the selected digital twin.

The API must never assume fixed sensor names.

---

# Error Format

All errors should use a consistent structure.

```json
{
  "error": {
    "code": "CONTEST_NOT_FOUND",
    "message": "Contest does not exist"
  }
}
```

---

# HTTP Status Codes

```text
200 OK
201 Created
204 No Content

400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict
422 Validation Error

500 Internal Server Error
```

---

# OpenAPI Support

The API must automatically expose:

```text
/ docs
/ redoc
```

through FastAPI.

---

# Design Requirement

The API layer must remain completely independent from:

- Digital Twin implementations
- Sensors
- Fault models
- Physical domains

The API should only interact with abstractions exposed by the EPIC Core.

This ensures that new digital twins, sensors and contest types can be introduced without changing the API structure.