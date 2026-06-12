# EPIC - ELIOS Predictive Intelligence Challenge

EPIC is a competition platform for predictive intelligence on live digital
twins. It turns a simulated physical system into a real-time machine learning
challenge: participants connect to sensor streams, collect their own data,
predict a hidden future window, and are scored automatically against ground
truth that is recorded by the platform but never shown to participants.

| Resource | URL |
|---|---|
| Live platform | https://epic.elioslab.net |
| REST API | https://epic.elioslab.net/api/v1 |
| OpenAPI / Swagger | https://epic.elioslab.net/docs |
| Participant SDK | `pip install epic-elios-client` |

EPIC is built for classrooms, research benchmarks, and industrial AI
experiments where static datasets are too simple. An organizer can choose a
digital twin, configure sensors and faults, invite participants, run a contest,
and get a live leaderboard without writing backend code.

## Contents

- [Concept](#concept)
- [Architecture](#architecture)
- [How a Contest Works](#how-a-contest-works)
- [Roles and Account Flow](#roles-and-account-flow)
- [Participant Quickstart](#participant-quickstart)
- [Organizer Workflow](#organizer-workflow)
- [Administrator Workflow](#administrator-workflow)
- [Scoring Model](#scoring-model)
- [Built-in Twins and Sensors](#built-in-twins-and-sensors)
- [API and WebSocket Surface](#api-and-websocket-surface)
- [Local Development](#local-development)
- [Testing](#testing)
- [Extending EPIC](#extending-epic)
- [Roadmap](#roadmap)

## Concept

Most machine learning competitions start with a file. EPIC starts with a
system.

That system is a digital twin: a compact simulation of a physical asset such as
a mass-spring-damper, a centrifugal pump, an electric motor, a gearbox, or a
smart building. The twin evolves in real wall-clock time. Sensors observe it
through a configurable measurement pipeline: noise, bias, drift, latency,
quantization, saturation, false readings, and outliers. Faults are scheduled
inside the twin and alter the latent physics.

Participants only receive the sensor stream. They do not receive the clean
state, fault labels, or future observations. EPIC stores those private signals
for scoring and keeps the competition honest by closing the stream before the
evaluation window is generated. A participant must forecast the future from
what they observed, not from what the server has already revealed.

The result is a richer contest format than a static benchmark. Students and
researchers practice the whole predictive-intelligence loop: instrumentation,
data collection, temporal reasoning, modelling, submission integrity, and live
leaderboard feedback.

## Architecture

EPIC separates competition infrastructure from simulated domains.

![EPIC architecture](assets/diagrams/epic-architecture.svg)

```text
Browser / SDK
    |
FastAPI REST + WebSocket API
    |
Contest, user, submission, scoring, leaderboard routers
    |
SimulationEngine + ContestBroadcaster
    |
DigitalTwin plugins + Sensor plugins + Metric / TaskEvaluator plugins
    |
SQLAlchemy models + Alembic migrations
```

Repository layout:

```text
epic/
├── epic/core/       interfaces, registries, engine, broadcaster, db, auth
├── epic/api/        FastAPI app, routers, schemas, templates, email service
├── epic/twins/      built-in digital twin packages
├── epic/sensors/    reusable scalar sensors
├── epic/gui/        static single-page web app served by FastAPI
├── epic_client/     standalone participant SDK package
├── notebooks/       participant notebooks
├── alembic/         database migrations
└── tests/           core, API, twin, sensor, and UI tests
```

Important design boundaries:

- `epic.core` is domain-independent.
- Twins own physical dynamics and fault effects.
- Sensors own measurement corruption.
- The engine streams only participant-visible sensor readings.
- Evaluation observations store private `ground_truth` and `labels`.
- Registries hold prototypes; sessions run independent copies.
- Production schema management is Alembic-only.

## How a Contest Works

An EPIC contest moves through a lifecycle:

```text
DRAFT -> SCHEDULED -> ACTIVE -> CLOSED -> ARCHIVED
  |                       |
  +-------> ACTIVE        v
                        PAUSED -> ACTIVE
                           |
                           +-------> CLOSED
```

The active phase is split into three time windows.

| Window | Time Range | What Happens |
|---|---|---|
| Observation | `start_date` to `end_of_observation` | The simulation runs and registered participants receive sensor readings over WebSocket. |
| Evaluation | `end_of_observation` for `prediction_horizon_seconds` | The simulation continues, the stream is closed, and private ground truth is recorded. |
| Submission | after evaluation until `end_date` | Participants submit forecasts for the hidden evaluation window. |

For forecasting contests, EPIC computes:

```text
eval_steps = round(prediction_horizon_seconds * sampling_rate_hz)
```

Each forecast target must contain exactly `eval_steps` values. Organizers choose
the required target variables with `target_variables`, a non-empty subset of
configured sensor ids. Other sensors can still be streamed as explanatory
features, but they do not affect the score.

## Roles and Account Flow

| Role | Scope |
|---|---|
| `PARTICIPANT` | Join contests, stream data, submit forecasts, view own submissions and scores. |
| `ORGANIZER` | Create and manage own contests, invite participants, inspect submissions, pause and resume sessions. |
| `ADMINISTRATOR` | Manage users, organizer requests, all contests, impersonation, and platform operations. |

Account creation is intentionally controlled:

- Organizers submit a public request at `POST /api/v1/organizer-requests`.
  Administrators approve or reject it.
- Participants join through contest invitations. An organizer sends invitations
  with `POST /api/v1/contests/{contest_id}/invitations`; the invitee accepts a
  one-time token and is registered for that contest.
- Administrators can create users directly with `POST /api/v1/users`.
- A bootstrap administrator can be seeded at startup with `ADMIN_USERNAME` and
  `ADMIN_PASSWORD`.

## Participant Quickstart

Install the SDK:

```bash
pip install epic-elios-client
```

Minimal forecasting workflow:

```python
import asyncio
from epic_client import EPICClient


async def main():
    client = EPICClient("https://epic.elioslab.net")
    client.login("your-username", "your-password")

    contests = client.list_contests(status="ACTIVE")
    contest = contests[0]
    contest_id = contest["contest_id"]

    task_config = contest["tasks"][0]["configuration"]
    eval_steps = task_config["eval_steps"]
    target_variables = task_config["target_variables"]

    client.register(contest_id)
    observations = await client.collect(contest_id, duration_seconds=120)

    last = observations[-1]["sensors"]
    forecast = {
        target: [last[target]] * eval_steps
        for target in target_variables
    }

    submission = client.submit(
        contest_id=contest_id,
        task_id="forecasting",
        payload={"forecast": forecast},
    )
    print(submission)

asyncio.run(main())
```

More participant material:

- SDK package README: [`epic_client/README.md`](epic_client/README.md)
- General notebook: [`notebooks/quickstart.ipynb`](notebooks/quickstart.ipynb)
- Mass-spring-damper example:
  [`notebooks/mass_spring_damper_forecasting.ipynb`](notebooks/mass_spring_damper_forecasting.ipynb)

## Organizer Workflow

The organizer dashboard is the normal contest-authoring surface.

1. Request organizer access and wait for administrator approval.
2. Create a contest from a template or from scratch.
3. Choose the twin, sensors, target variables, faults, initial conditions,
   scoring metric, and dates.
4. Activate or schedule the contest.
5. Invite participants.
6. Monitor registrations, submissions, scores, and leaderboard entries.
7. Pause, resume, extend, close, delete, or archive the contest as needed.

Contest creation is configuration-driven. A representative request:

```json
{
  "name": "Pump Bearing Wear Challenge",
  "description": "Forecast flow and vibration during progressive bearing wear.",
  "visibility": "PUBLIC",
  "task_type": "FORECASTING",
  "metric_ids": ["mae"],
  "twin_id": "industrial_pump",
  "sensor_configs": [
    {"sensor_id": "flow_rate", "noise_std": 0.2},
    {"sensor_id": "pressure", "noise_std": 0.02},
    {"sensor_id": "temperature", "noise_std": 0.05},
    {"sensor_id": "vibration", "noise_std": 0.03}
  ],
  "target_variables": ["flow_rate", "vibration"],
  "fault_schedule": [
    {
      "fault_id": "bearing_wear",
      "start_time": 20.0,
      "end_time": null,
      "severity": 0.7
    }
  ],
  "initial_conditions": {
    "flow_rate": 120.0,
    "pressure": 4.0,
    "wear": 0.05
  },
  "sampling_rate_hz": 10.0,
  "score_against": "ground_truth",
  "start_date": "2027-01-10T09:00:00Z",
  "end_of_observation": "2027-01-10T09:30:00Z",
  "prediction_horizon_seconds": 60.0,
  "end_date": "2027-01-10T09:40:00Z"
}
```

The API stores the scoring configuration as a contest `Task`. Responses include
`tasks[0].configuration.eval_steps`, `target_variables`,
`prediction_horizon_seconds`, and `score_against`.

Templates are available at `GET /api/v1/templates`. Each template includes a
twin id, compatible sensors, fault schedule, initial conditions, sampling rate,
task type, and target variables.

## Administrator Workflow

Administrators operate the whole platform. They can:

- approve or reject organizer requests;
- create, suspend, restore, delete, and promote users;
- impersonate active users for support;
- manage any contest regardless of owner;
- inspect all sessions, submissions, scores, and leaderboards;
- configure bootstrap admin and SMTP notification settings.

The administrator dashboard lives in the static web app under
`epic/gui/index.html`.

## Scoring Model

The implemented task evaluator is `FORECASTING`.

A submission payload contains one list per required target variable:

```json
{
  "forecast": {
    "position": [0.12, 0.13, 0.14],
    "velocity": [1.8, 1.7, 1.6]
  }
}
```

Validation rules:

- every configured target variable must be present;
- each list must contain exactly `eval_steps` values;
- values must be numeric;
- extra forecast keys are accepted but ignored for scoring.

Task configuration:

| Field | Meaning |
|---|---|
| `eval_steps` | Number of predicted values per target variable. |
| `target_variables` | Configured sensor ids required and scored. |
| `score_against` | `ground_truth` or `sensors`. |
| `metric_ids` | Registered metrics to compute. |

`ground_truth` compares against clean latent values recorded before sensor
corruption. `sensors` compares against noisy sensor readings when the contest is
about predicting the measured signal itself.

Built-in metrics:

| Metric | Direction | Purpose |
|---|---|---|
| `mae` | minimize | Mean absolute error for forecasting. |
| `f1` | maximize | Binary F1 score for anomaly-detection style tasks. |

Leaderboards keep each participant's best evaluated submission, respecting the
metric direction.

## Built-in Twins and Sensors

Digital twins implement `DigitalTwin` and live under `epic/twins/`. Each twin is
self-contained: it owns state evolution, fault activation, and fault effects.

| Twin ID | System | Quantities | Faults |
|---|---|---|---|
| `mass_spring_damper` | Mechanical oscillator | `position`, `velocity`, `acceleration`, `temperature` | `increased_damping`, `reduced_stiffness`, `increased_friction` |
| `industrial_pump` | Centrifugal pump | `flow_rate`, `pressure`, `temperature`, `vibration` | `cavitation`, `bearing_wear`, `filter_clog` |
| `electric_motor` | Three-phase induction motor | `current`, `voltage`, `rotational_speed`, `temperature` | `overheating`, `bearing_fault`, `voltage_imbalance` |
| `rotating_machinery` | Shaft and gearbox | `rotational_speed`, `vibration`, `temperature`, `power` | `unbalance`, `misalignment`, `gear_tooth_wear` |
| `smart_building` | HVAC-managed floor | `temperature`, `humidity`, `co2_concentration`, `occupancy` | `hvac_failure`, `sensor_drift`, `occupancy_spike` |

The runtime source of truth is the catalog API:

```text
GET /api/v1/catalog
GET /api/v1/catalog/{twin_id}
```

Registered scalar sensors:

| Sensor ID | Unit | Typical Use |
|---|---|---|
| `position` | m | Mechanical displacement |
| `velocity` | m/s | Linear velocity |
| `acceleration` | m/s2 | Linear acceleration |
| `temperature` | deg C | Thermal behaviour |
| `flow_rate` | m3/h | Pump flow |
| `pressure` | bar | Fluid pressure |
| `vibration` | mm/s | Machinery health |
| `current` | A | Motor current |
| `voltage` | V | Electrical supply |
| `rotational_speed` | RPM | Shaft or motor speed |
| `power` | W | Mechanical or electrical power |
| `humidity` | %RH | Building environment |
| `co2_concentration` | ppm | Indoor air quality |
| `occupancy` | people | Building load |

Each sensor supports the same measurement-pipeline parameters:

| Parameter | Effect |
|---|---|
| `noise_std` | Gaussian noise. |
| `gain` | Multiplicative calibration factor. |
| `bias` | Additive offset. |
| `drift_rate` | Time-dependent drift. |
| `min_value`, `max_value` | Saturation bounds. |
| `quantization` | Rounding step. |
| `latency_steps` | Delayed output. |
| `p_false_reading` | Probability of replacing the reading with a false value. |
| `p_outlier` | Probability of injecting a large outlier. |

The registry stores sensor prototypes. The engine creates a fresh configured
sensor instance for each session so drift, buffers, and random state never leak
between contests.

## API and WebSocket Surface

The endpoint-level contract is generated by FastAPI at `/docs`. All protected
REST endpoints use:

```text
Authorization: Bearer <JWT>
```

Core route groups:

| Area | Routes |
|---|---|
| Auth | `POST /api/v1/auth/login`, `GET /api/v1/auth/me` |
| Users | `POST/GET /api/v1/users`, `GET/PATCH/DELETE /api/v1/users/{user_id}`, impersonation |
| Organizer requests | public request creation, admin list/approve/reject |
| Contests | create, list, read, update status/deadline, pause, resume, delete |
| Invitations | create/list/revoke contest invitations, validate/accept public token |
| Registrations | join, list, inspect, withdraw/remove |
| Streaming | `WS /api/v1/ws/contests/{contest_id}?token=...` |
| Submissions | create/list/read submissions and scores |
| Leaderboards | public contest leaderboard and permission-checked user entry |
| Metadata | templates, catalog, twin metadata, compatible sensors, faults |

Business-rule failures use a stable error envelope:

```json
{
  "error": {
    "code": "CONTEST_STATE_ERROR",
    "message": "Contest is not active"
  }
}
```

Common error codes include `INVALID_CREDENTIALS`, `FORBIDDEN`,
`CONTEST_NOT_FOUND`, `CONTEST_STATE_ERROR`, `REGISTRATION_ERROR`,
`SUBMISSION_ERROR`, `VALIDATION_ERROR`, `PLUGIN_NOT_FOUND`, and
`PLUGIN_EXECUTION_ERROR`.

### WebSocket Messages

Participants connect with the token in the query string:

```text
wss://<host>/api/v1/ws/contests/{contest_id}?token=<JWT>
```

Observation messages:

```json
{
  "timestamp": "2027-01-15T10:00:00.500000+00:00",
  "session_id": "8d44f402-0000-0000-0000-000000000000",
  "sequence_id": 116,
  "committed_through": 110,
  "sensors": {
    "position": 0.15,
    "velocity": 1.82
  }
}
```

`sequence_id` increments every simulation step. `committed_through` is the
highest sequence safely flushed to the database. The stream never includes
ground truth, labels, or the twin's internal state.

When the observation phase ends, the server sends:

```json
{
  "event": "evaluation_started",
  "observation_end_sequence_id": 400,
  "evaluation_steps": 20
}
```

Then it closes the stream. If a contest is closed early, the server sends:

```json
{ "event": "contest_closed" }
```

## Local Development

Requirements:

- Python 3.11 or later
- `uv`
- SQLite for local development, PostgreSQL for production

Install:

```bash
git clone https://github.com/Elios-Lab/epic.git
cd epic
uv sync
```

Create `.env`:

```env
DATABASE_URL=sqlite+aiosqlite:///./epic.db
SECRET_KEY=change-me-in-production
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me
BASE_URL=http://localhost:8000
```

Run migrations:

```bash
set -a
source .env
set +a
uv run alembic upgrade head
```

Start the server:

```bash
uv run uvicorn "epic.api.main:create_app" --factory --reload
```

Open:

- Web UI: http://localhost:8000
- Swagger UI: http://localhost:8000/docs

Useful optional settings:

| Variable | Default | Purpose |
|---|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT lifetime |
| `SESSION_QUEUE_CAPACITY` | `1000` | Per-client WebSocket queue |
| `BASE_URL` | `http://localhost:8000` | Invitation link base URL |
| `SMTP_HOST` | unset | Enables email notifications when configured |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_TLS` | `true` | STARTTLS |

## Testing

Default suite:

```bash
uv run pytest tests/ --tb=short -q
```

Focused suites:

```bash
uv run pytest tests/core
uv run pytest tests/api
uv run pytest tests/twins
uv run pytest tests/sensors
uv run pytest epic_client/tests
```

The Playwright UI suite is excluded from the default run:

```bash
uv run pytest tests/ui
```

API tests use a per-test SQLite database, fresh plugin registries, FastAPI
`TestClient`, and a collecting notification service. They must not use
production settings or production registries.

## Extending EPIC

### Add a Digital Twin

Implement `DigitalTwin`:

```python
class DigitalTwin:
    twin_id: str
    name: str
    def configure(self, initial_conditions: dict | None, fault_schedule: list[dict]) -> SimulationState: ...
    def step(self, state: SimulationState, dt: float) -> SimulationState: ...
    def get_active_faults(self) -> list[dict]: ...
    def supported_quantities(self) -> set[PhysicalQuantity]: ...
    def get_faults(self) -> list[FaultDescriptor]: ...
    def metadata(self) -> dict: ...
```

Register it:

```python
import epic.core.registry as registry_module
from my_twin import MyTwin

registry_module.twin_registry.register(MyTwin())
```

### Add a Sensor

Implement `Sensor`, declare `measured_quantity`, and register it with
`sensor_registry`. If the quantity already exists in `PhysicalQuantity`, no Core
change is needed. New quantities belong in `epic/core/quantities.py`.

### Add a Metric

Implement `ScoringMetric` and register it with `metric_registry`:

```python
class MyMetric(ScoringMetric):
    metric_id = "my_metric"
    direction = "minimize"
    def compute(self, y_true, y_pred) -> float: ...
    def metadata(self) -> dict: ...
```

### Add a Task Type

Implement `TaskEvaluator` and register it with `task_evaluator_registry`. A task
evaluator owns payload validation, metric application, and the leaderboard
ranking value for one task type.

## Roadmap

Implemented:

- domain-independent interfaces and plugin registries;
- FastAPI backend with JWT authentication;
- organizer requests, participant invitations, admin user management, and
  impersonation;
- two-phase forecasting contests with WebSocket observation streams;
- pause, resume, close, restart recovery, and session isolation;
- configurable sensors and fault schedules;
- target-variable forecasting with automatic scoring and leaderboards;
- contest templates and twin catalog API;
- static role-based GUI;
- PyPI-ready participant SDK and notebooks.

Planned:

- anomaly detection, fault classification, and remaining-useful-life task
  evaluators;
- public/private leaderboard splits;
- runtime plugin governance;
- larger-scale distributed simulation;
- more digital twin domain packs.

## Credits

EPIC is developed by Elios Lab at the University of Genoa.

The long-term goal is simple: a new competition should be configuration, not
backend code; and a new application domain should be a plugin, not a rewrite.
