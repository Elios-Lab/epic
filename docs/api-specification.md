# API Conventions and WebSocket Protocol

The complete, always-current REST endpoint reference is the **interactive OpenAPI documentation** served by the platform itself at [`/docs`](https://epic.elioslab.net/docs). Every route declares Pydantic request and response models, so the generated schema is the contract (request bodies, response shapes, and status codes included). This document deliberately does not duplicate it. What lives here instead is everything OpenAPI cannot express: the cross-cutting conventions all endpoints share, and the full WebSocket streaming protocol.

---

## Conventions

**Versioning.** All REST endpoints are mounted under `/api/v1`. Breaking changes will be introduced under a new version prefix; `v1` responses may gain fields over time but existing fields will not change meaning or disappear.

**Authentication.** Protected endpoints expect a JWT bearer token in the `Authorization: Bearer <token>` header, obtained from `POST /api/v1/auth/login`. Tokens carry the user id (`sub`), username, and role, and expire after a configurable lifetime (one hour by default). The only unauthenticated endpoints are login, the organizer request form, and invitation validation/acceptance. See [Authentication](authentication.md) for roles and the permission model.

**Error envelope.** Every business-rule failure returns a consistent JSON envelope with an HTTP status mapped from the exception type:

```json
{
  "error": {
    "code": "CONTEST_STATE_ERROR",
    "message": "Contest is not active"
  }
}
```

Validation failures of the request *shape* (missing fields, wrong types) are FastAPI's standard `422` response with a `detail` array. Error codes are uppercase snake-case strings and are stable across versions — clients may depend on them for programmatic error handling. The full mapping from the exception hierarchy in `epic_core/exceptions.py`:

| Exception | HTTP Status | Error Code |
|---|---|---|
| `PluginNotFoundError` | 404 | `PLUGIN_NOT_FOUND` |
| `SessionNotFoundError` | 404 | `SESSION_NOT_FOUND` |
| `ContestNotFoundError` | 404 | `CONTEST_NOT_FOUND` |
| `ContestStateError` | 409 | `CONTEST_STATE_ERROR` |
| `SessionStateError` | 409 | `SESSION_STATE_ERROR` |
| `RegistrationError` | 409 | `REGISTRATION_ERROR` |
| `SubmissionError` | 422 | `SUBMISSION_ERROR` |
| `EPICValidationError` | 422 | `VALIDATION_ERROR` |
| `InvalidCredentialsError` | 401 | `INVALID_CREDENTIALS` |
| `InsufficientPermissionsError` | 403 | `FORBIDDEN` |
| `PluginValidationError` | 500 | `PLUGIN_VALIDATION_ERROR` |
| `PluginExecutionError` | 500 | `PLUGIN_EXECUTION_ERROR` |
| Any other `EPICError` | 500 | `INTERNAL_ERROR` |

Unhandled Python exceptions (bugs in the platform itself) return `500` with a generic message; stack traces are never included in API responses outside `DEBUG` mode.

**Pagination.** List endpoints that can grow unboundedly (users, contests, organizer requests) accept `limit` (default 100, max 1000) and `offset` query parameters and return a `total` count alongside the page, so clients can paginate without a second query.

**Identifiers and timestamps.** All entity identifiers are UUIDs serialized as strings. All timestamps are ISO-8601 strings in UTC; datetimes submitted to the API may carry an explicit offset or be naive (naive values are interpreted as UTC).

**Plugin metadata is open.** Endpoints that return twin, sensor, fault, or template metadata guarantee the documented minimum fields (`*_id`, `name`, `version`, `description`, plus type-specific fields like a sensor's `unit` and `measured_quantity`) but may carry additional keys contributed by the plugin. Clients must ignore unknown fields.

---

## WebSocket Streaming Protocol

OpenAPI does not describe WebSocket endpoints, so this section is the authoritative specification of the contest stream.

### Endpoint and authentication

```text
ws(s)://<host>/api/v1/ws/contests/{contest_id}?token=<JWT>
```

The JWT is passed as a query parameter (browser WebSocket clients cannot set headers). The server validates it during the handshake and closes with code **1008** if the token is missing, invalid, or expired.

### Authorization

A valid token is necessary but not sufficient. The contest must be ACTIVE and still in its observation phase, and the connecting user must be entitled to the stream: administrators may connect to any contest, organizers only to contests they created, and participants only when they hold an active registration for this contest. Any other combination closes with **1008** during the handshake. In two-phase contests, connections attempted after `end_of_observation` are rejected the same way, evaluation-phase data is never streamed.

### Observation messages

During the observation phase the server pushes one JSON message per simulation step:

```json
{
  "timestamp": "2027-01-15T10:00:00.500Z",
  "session_id": "8d44f402-…",
  "sequence_id": 116,
  "committed_through": 110,
  "sensors": {
    "position": 0.15,
    "velocity": 1.82,
    "temperature": 31.5
  }
}
```

`sequence_id` increments by one per step with no gaps at the source; a client that observes a gap missed messages (slow consumer or reconnect) and cannot recover them, the server never replays. `committed_through` is the highest sequence number guaranteed to be flushed to the database; clients that anchor anything to observation history should use it rather than the live `sequence_id`. The `sensors` object carries one numeric reading per configured sensor, keyed by sensor id, clients must not assume a fixed set of keys. Ground-truth values, fault labels, and the twin's internal state are never present in any message.

### Control events

Two event messages interrupt the observation stream, each followed by a server-side close:

```json
{ "event": "evaluation_started", "observation_end_sequence_id": 400, "evaluation_steps": 20 }
```

sent exactly once when the observation phase ends. `evaluation_steps` is the number of values per sensor a forecast must contain; the submission window opens `prediction_horizon_seconds` later. And:

```json
{ "event": "contest_closed" }
```

sent when an organizer or administrator closes the contest while clients are connected. After either event the connection closes and reconnection attempts are rejected (1008), since the contest is no longer streaming.

### Back-pressure

Each client has a bounded server-side queue (1000 messages by default). A consumer too slow to keep up silently loses its **oldest** queued messages, detectable through `sequence_id` gaps. The simulation loop is never blocked by slow clients.

### Reconnection guidance

Clients should reconnect with backoff after unexpected disconnections during the observation phase, treat a 1008 close as permanent (authorization or phase change, not a transient fault), and treat `evaluation_started` and `contest_closed` as terminal for the stream. The published SDK (`epic-elios-client`) implements this behavior in `EPICClient.stream()` / `collect()`.

---

## Collecting Data Client-Side

EPIC does not generate or export datasets on the server — dataset collection is the participant's responsibility, by design. A core educational principle of the platform is that collecting data from a live system is itself a skill: participants connect to the stream, decide what to record and at what granularity, handle interruptions gracefully, and curate their own training dataset, exactly as an engineer instrumenting a real system would.

Two consequences of the protocol above shape that work. The server never replays missed observations — a dropped connection or a slow consumer means a permanent `sequence_id` gap — and a participant who connects after the contest started receives data only from that point forward. Earlier joiners who collected more data have a natural advantage, just as in real monitoring.

Storage is entirely a client-side choice: append each message to a CSV file, stream into a local database such as SQLite or DuckDB, or buffer in memory and write periodically. A minimal collector:

```python
import asyncio
import csv
import json

import websockets


async def collect(contest_id: str, token: str, output_path: str):
    url = f"wss://epic.elioslab.net/api/v1/ws/contests/{contest_id}?token={token}"
    with open(output_path, "w", newline="") as f:
        writer = None
        async with websockets.connect(url) as ws:
            async for message in ws:
                data = json.loads(message)
                row = {"timestamp": data["timestamp"],
                       "sequence_id": data["sequence_id"],
                       **data["sensors"]}
                if writer is None:
                    writer = csv.DictWriter(f, fieldnames=row.keys())
                    writer.writeheader()
                writer.writerow(row)
```

The published SDK wraps this pattern (with reconnection and CSV export) in `EPICClient.collect()`. The platform never needs to know how a participant stores or processes their data — the WebSocket stream is the only delivery mechanism, and everything downstream of it is a client-side concern.