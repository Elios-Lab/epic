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

Request:

```json
{
  "username": "student1",
  "email": "student@example.com",
  "password": "..."
}
```

Response `201 Created`:

```json
{
  "user_id": "u_abc123",
  "username": "student1",
  "email": "student@example.com",
  "role": "PARTICIPANT",
  "is_active": true,
  "created_at": "2027-01-01T10:00:00Z"
}
```

---

## Get User

```http
GET /api/v1/users/{user_id}
```

Response `200 OK`:

```json
{
  "user_id": "u_abc123",
  "username": "student1",
  "email": "student@example.com",
  "role": "PARTICIPANT",
  "is_active": true,
  "created_at": "2027-01-01T10:00:00Z"
}
```

---

## Update User

```http
PATCH /api/v1/users/{user_id}
```

Example request:

```json
{
  "email": "new_email@example.com"
}
```

---

## Delete User

```http
DELETE /api/v1/users/{user_id}
```

Response `204 No Content`.

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

Request:

```json
{
  "name": "EPIC Forecasting Challenge 2027",
  "description": "Introductory forecasting competition",
  "start_date": "2027-01-10T00:00:00Z",
  "end_date": "2027-03-01T23:59:59Z",
  "visibility": "PUBLIC"
}
```

Response `201 Created`:

```json
{
  "contest_id": "forecast_2027",
  "name": "EPIC Forecasting Challenge 2027",
  "status": "DRAFT",
  "visibility": "PUBLIC",
  "start_date": "2027-01-10T00:00:00Z",
  "end_date": "2027-03-01T23:59:59Z",
  "created_by": "u_admin",
  "created_at": "2027-01-01T12:00:00Z"
}
```

---

## Get Contest

```http
GET /api/v1/contests/{contest_id}
```

Response `200 OK`:

```json
{
  "contest_id": "forecast_2027",
  "name": "EPIC Forecasting Challenge 2027",
  "status": "ACTIVE",
  "visibility": "PUBLIC",
  "start_date": "2027-01-10T00:00:00Z",
  "end_date": "2027-03-01T23:59:59Z"
}
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

Response `200 OK`:

```json
{
  "registration_id": "reg_xyz",
  "contest_id": "forecast_2027",
  "user_id": "u_abc123",
  "registered_at": "2027-01-05T08:00:00Z",
  "status": "REGISTERED"
}
```

---

## Delete Registration

```http
DELETE /api/v1/contest-registrations/{registration_id}
```

Represents withdrawal from a contest. Response `204 No Content`.

---

# Leaderboards

Leaderboards are derived resources.

---

## Get Contest Leaderboard

```http
GET /api/v1/contests/{contest_id}/leaderboard
```

Response `200 OK`:

```json
{
  "contest_id": "forecast_2027",
  "entries": [
    {
      "rank": 1,
      "user_id": "u_abc123",
      "username": "student1",
      "submission_id": "sub_001",
      "score": 0.142,
      "updated_at": "2027-02-10T14:30:00Z"
    }
  ]
}
```

---

## Get User Ranking

```http
GET /api/v1/contests/{contest_id}/leaderboard/{user_id}
```

Response `200 OK`:

```json
{
  "rank": 1,
  "user_id": "u_abc123",
  "submission_id": "sub_001",
  "score": 0.142,
  "updated_at": "2027-02-10T14:30:00Z"
}
```

---

# Digital Twins

Digital twins are exposed as metadata resources.

---

## List Twins

```http
GET /api/v1/twins
```

Response `200 OK`:

```json
{
  "twins": [
    {
      "twin_id": "mechanical_system",
      "name": "Mechanical System",
      "version": "1.0.0",
      "description": "Simple mass-spring-damper example",
      "is_active": true
    }
  ]
}
```

---

## Get Twin

```http
GET /api/v1/twins/{twin_id}
```

Response `200 OK`:

```json
{
  "twin_id": "mechanical_system",
  "name": "Mechanical System",
  "version": "1.0.0",
  "description": "Simple mass-spring-damper example",
  "is_active": true,
  "metadata": {}
}
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

# Faults

Faults belong to digital twins and are exposed as read-only metadata resources.

---

## List Twin Faults

```http
GET /api/v1/twins/{twin_id}/faults
```

Response `200 OK`:

```json
{
  "twin_id": "mechanical_system",
  "faults": [
    {
      "fault_id": "increased_damping",
      "name": "Increased Damping",
      "version": "1.0.0",
      "description": "Gradual increase in damping coefficient"
    },
    {
      "fault_id": "sensor_bias",
      "name": "Sensor Bias",
      "version": "1.0.0",
      "description": "Constant offset added to sensor measurement"
    }
  ]
}
```

---

## Get Fault

```http
GET /api/v1/twins/{twin_id}/faults/{fault_id}
```

Response `200 OK`:

```json
{
  "fault_id": "increased_damping",
  "twin_id": "mechanical_system",
  "name": "Increased Damping",
  "version": "1.0.0",
  "description": "Gradual increase in damping coefficient",
  "metadata": {}
}
```

---

# Simulation Sessions

Each contest has one simulation session, created automatically when the contest becomes ACTIVE. Participants cannot create, modify, or delete sessions.

---

## Get Contest Session

```http
GET /api/v1/contests/{contest_id}/session
```

Returns the current simulation session for a contest.

Response `200 OK`:

```json
{
  "session_id": "sess_abc",
  "contest_id": "forecast_2027",
  "twin_id": "mechanical_system",
  "scenario_id": "normal_operation",
  "sampling_rate_hz": 10.0,
  "status": "RUNNING",
  "started_at": "2027-01-10T00:00:00Z",
  "ended_at": null
}
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

`prediction_from_sequence` is required. It must be the `sequence_id` of the last observation the participant used to build their prediction. The server rejects the submission if this sequence_id had not yet been published at the time of submission. See [Scoring](scoring.md) for a full explanation of the temporal integrity guarantee.

Request:

```json
{
  "task_id": "forecasting",
  "prediction_from_sequence": 500,
  "payload": {
    "forecast": {
      "horizon_1": { "position": 0.12 },
      "horizon_5": { "position": 0.24 }
    }
  }
}
```

Response `201 Created`:

```json
{
  "submission_id": "sub_001",
  "contest_id": "forecast_2027",
  "user_id": "u_abc123",
  "task_id": "forecasting",
  "prediction_from_sequence": 500,
  "submitted_at": "2027-02-10T14:00:00Z",
  "status": "PENDING"
}
```

---

## Get Submission

```http
GET /api/v1/submissions/{submission_id}
```

Response `200 OK`:

```json
{
  "submission_id": "sub_001",
  "contest_id": "forecast_2027",
  "user_id": "u_abc123",
  "task_id": "forecasting",
  "submitted_at": "2027-02-10T14:00:00Z",
  "status": "EVALUATED"
}
```

---

## Delete Submission

```http
DELETE /api/v1/submissions/{submission_id}
```

If contest rules allow it. Response `204 No Content`.

---

# Scores

Scores are derived resources generated from submissions.

---

## Get Submission Scores

```http
GET /api/v1/submissions/{submission_id}/scores
```

Response `200 OK`:

```json
{
  "submission_id": "sub_001",
  "scores": [
    {
      "score_id": "sc_001",
      "metric_id": "mae",
      "value": 0.142,
      "computed_at": "2027-02-10T14:05:00Z"
    },
    {
      "score_id": "sc_002",
      "metric_id": "rmse",
      "value": 0.201,
      "computed_at": "2027-02-10T14:05:00Z"
    }
  ]
}
```

---

## Get Contest Scores

```http
GET /api/v1/contests/{contest_id}/scores
```

Administrator only.

---

# WebSocket API

The WebSocket stream is the primary way participants interact with a contest simulation. Participants connect to receive live sensor readings in real time.

---

## Contest Stream

```text
WS /api/v1/ws/contests/{contest_id}
```

Authentication: JWT token passed as a query parameter or `Authorization` header.

The server streams one JSON message per simulation tick:

```json
{
  "timestamp": "2027-01-15T10:00:00.500Z",
  "session_id": "sess_abc",
  "sequence_id": 500,
  "sensors": {
    "position": 0.15,
    "velocity": 1.82,
    "temperature": 31.5
  }
}
```

The sensor keys are determined by the digital twin configured for the contest. The API never assumes fixed sensor names.

Labels and fault metadata are never included in WebSocket messages. Participants are responsible for collecting and storing the received sensor readings client-side.

If the contest is not ACTIVE, the server closes the connection immediately with an appropriate error code.

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