# EPIC — ELIOS Predictive Intelligence Challenge

> A simulation-driven machine learning competition platform built on extensible digital twins, real-time sensor streaming, and automated evaluation.

**Live instance: [https://epic.elioslab.net](https://epic.elioslab.net)**

| Endpoint | URL |
|---|---|
| Web interface | `https://epic.elioslab.net` |
| REST API | `https://epic.elioslab.net/api/v1` |
| Swagger UI | `https://epic.elioslab.net/docs` |

---

## What is EPIC?

EPIC (ELIOS Predictive Intelligence Challenge) is a framework for running machine learning competitions based on simulated physical systems — called **digital twins**. Rather than handing participants a static CSV file, EPIC runs a simulation in real time and lets participants collect their own data by streaming live sensor readings over a WebSocket connection. Participants then train predictive models and submit forecasts to be scored against hidden ground-truth trajectories.

The platform is designed to support:

- **Education** — professors set up contests for their students without writing code
- **Research** — researchers benchmark algorithms on reproducible simulation scenarios
- **Industrial AI experimentation** — realistic predictive maintenance and anomaly detection challenges

The currently supported ML task is **time-series forecasting**, scored with MAE. Anomaly detection, fault diagnosis, predictive maintenance, prognostics, and remaining useful life estimation are planned for future releases.

---

## How a contest works

Every EPIC contest follows a **two-phase structure**:

### Phase 1 — Observation window

From `start_date` to `end_of_observation`, the digital twin simulation runs in real time and broadcasts sensor readings to all registered participants via WebSocket. This is the data-collection window. Participants receive timestamped sensor observations and use them to train a predictive model.

### Phase 2 — Evaluation window

From `end_of_observation` to `end_of_observation + prediction_horizon_seconds`, the simulation keeps running but the sensor stream is closed. The ground-truth values for this window are recorded by the platform but hidden from participants. This prevents any post-hoc prediction.

### Submission window

Once the evaluation window ends, participants submit a forecast covering every time step of the evaluation window. Submissions are scored automatically against the ground truth and the leaderboard is updated immediately.

The number of values to predict per sensor is:

```
eval_steps = round(prediction_horizon_seconds × sampling_rate_hz)
```

---

## Participating

### Install the SDK

```bash
pip install epic-elios-client
```

### Quick example

```python
import asyncio
from epic_client import EPICClient

async def main():
    client = EPICClient("https://epic.elioslab.net")
    client.login("your-username", "your-password")

    # Find an active contest and read how many steps to forecast
    contests = client.list_contests(status="ACTIVE")
    contest_id = contests[0]["contest_id"]
    eval_steps = contests[0]["tasks"][0]["configuration"]["eval_steps"]

    client.register(contest_id)

    # Collect live sensor data during the observation phase
    observations = await client.collect(contest_id, duration_seconds=120)

    # Build a forecast (replace with your model)
    last = observations[-1]["sensors"]
    forecast = {sensor: [value] * eval_steps for sensor, value in last.items()}

    # Submit
    result = client.submit(
        contest_id=contest_id,
        task_id="forecasting",
        payload={"forecast": forecast},
    )
    print("Submitted:", result["submission_id"])

asyncio.run(main())
```

Full SDK documentation and a step-by-step Jupyter notebook are available in the [`epic_client/`](epic_client/README.md) package and in [`notebooks/quickstart.ipynb`](notebooks/quickstart.ipynb).

---

## Architecture

EPIC separates three concerns that are often entangled in similar platforms:

1. **Competition management** — contest lifecycle, user registration, submission handling, scoring, and leaderboards
2. **Simulation infrastructure** — the real-time engine that drives digital twins at a configurable sampling rate and fans out sensor readings to all connected participants via WebSocket
3. **Digital twin implementations** — self-contained physical models with their own fault management, decoupled from both the engine and the contest logic

This separation means a new twin, sensor, or fault model can be introduced by implementing a small interface and registering it at startup — no changes to the platform core are required.

### Key components

| Component | Description |
|---|---|
| `epic_core` | Interfaces, plugin registries, simulation engine, WebSocket broadcaster, database models, authentication |
| `epic_api` | FastAPI application — REST and WebSocket routers, dependency injection, error handling |
| `epic_twins` | Digital twin implementations (mass-spring-damper, pump, electric motor, rotating machinery, smart building) |
| `epic_sensors` | Sensor implementations, decoupled from twins via a physical-quantity ontology |
| `epic_client` | Participant Python SDK published on PyPI |
| `epic_gui` | Single-page web frontend with role-based dashboards |
| `alembic` | Database migration scripts |
| `docs` | Architecture, API, and authoring documentation |
| `notebooks` | Jupyter notebooks for participants |
| `tests` | Unit, integration, and end-to-end API tests |

### Repository structure

```text
epic/
├── epic_core/              ← interfaces, registry, engine, broadcaster, db models, auth
│   ├── db/                 ← SQLAlchemy models and Alembic migrations
│   └── quantities.py       ← PhysicalQuantity ontology (shared by sensors and twins)
├── epic_api/               ← FastAPI application and routers
│   └── routers/            ← auth, users, contests, registrations, submissions, ws, …
├── epic_twins/             ← digital twins (state, dynamics, fault management)
│   ├── mass_spring_damper/
│   ├── industrial_pump/
│   ├── electric_motor/
│   ├── rotating_machinery/
│   └── smart_building/
├── epic_sensors/           ← reusable sensors, independent of specific twins
├── epic_gui/               ← single-page web frontend
├── epic_client/            ← participant SDK (published on PyPI)
├── alembic/                ← database migrations
├── docs/                   ← architecture and API documentation
├── notebooks/              ← Jupyter quickstart and example notebooks
└── tests/                  ← unit, integration, and API tests
```

---

## Digital twins

EPIC ships with five digital twins covering a range of industrial domains:

| Twin | Domain | Physical quantities |
|---|---|---|
| **Mass-Spring-Damper** | Mechanical | Position, velocity, acceleration |
| **Industrial Pump** | Fluid machinery | Flow rate, pressure, vibration, temperature |
| **Electric Motor** | Electrical machinery | Current, voltage, RPM, temperature |
| **Rotating Machinery** | Shaft and gearbox | Vibration, power, speed, temperature |
| **Smart Building** | HVAC and energy | Temperature, humidity, CO₂, occupancy |

Each twin is fully self-contained: it manages its own physical state, fault injection, and sensor compatibility. Adding a new twin requires only implementing the `DigitalTwin` interface — no changes to EPIC Core.

---

## Getting started (self-hosting)

### Prerequisites

- Python 3.11 or later
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- A supported database (SQLite for development, PostgreSQL for production)

### 1. Clone and install

```bash
git clone https://github.com/Elios-Lab/epic.git
cd epic
uv sync
```

### 2. Configure the environment

Create a `.env` file in the project root:

```env
DATABASE_URL=sqlite+aiosqlite:///./epic.db
SECRET_KEY=change-me-in-production
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me
```

For production, use a PostgreSQL URL:

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/epic
```

### 3. Run database migrations

```bash
set -a && source .env && set +a
alembic upgrade head
```

### 4. Start the server

```bash
uv run uvicorn "epic_api.main:create_app" --factory --reload
```

The web interface is at `http://localhost:8000` and the Swagger UI at `http://localhost:8000/docs`.

### 5. Run the tests

```bash
uv run pytest
```

---

## Authoring a contest

Contests are created through the web interface (Organizer or Administrator role) or via the REST API. The fastest path is to start from a **contest template** — a predefined configuration for a specific twin that sets sensor configs, fault schedule, initial conditions, and scoring parameters.

Templates are listed at `GET /api/v1/templates` and can be loaded directly from the web UI's contest creation form.

For a full guide on configuring sensors, faults, and scoring from scratch, see [Contest Authoring](docs/contest-authoring.md).

---

## Extending EPIC

### Adding a digital twin

Implement the `DigitalTwin` interface and register it at application startup:

```python
from epic_core.registry import twin_registry
from my_package import MyTwin

twin_registry.register(MyTwin())
```

The new twin appears automatically at `GET /api/v1/twins` and can immediately be used in contest configurations. No other changes are needed. See [Digital Twins](docs/digital-twins.md) for the full interface specification.

### Adding a sensor

Implement the `Sensor` interface, declare the physical quantity it measures, and register it with `sensor_registry`. As long as the measured quantity is supported by the target twin, the sensor can be used in any contest configuration. See [Sensors](docs/sensors.md).

### Adding a fault model

Fault models are defined inside the twin that owns them, keeping physical realism self-contained. See [Faults](docs/faults.md).

### Adding a scoring metric

Implement the `ScoringMetric` interface and register it with `metric_registry`. New metrics become available in the `metric_ids` field of the contest creation request. See [Scoring](docs/scoring.md).

---

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | High-level system architecture and component responsibilities |
| [Domain Model](docs/domain-model.md) | Canonical entity definitions and database schema |
| [Physical Quantities](docs/quantities.md) | Ontology shared between sensors and digital twins |
| [Simulation Engine](docs/simulation-engine.md) | Simulation loop, two-phase model, WebSocket streaming |
| [API Specification](docs/api-specification.md) | Complete REST and WebSocket API reference |
| [Authentication](docs/authentication.md) | JWT, role-based access control, user management |
| [Configuration](docs/configuration.md) | All environment variables and their defaults |
| [Error Handling](docs/error-handling.md) | Exception hierarchy and API error envelope |
| [Testing](docs/testing.md) | Testing strategy, fixtures, and end-to-end tests |
| [Digital Twins](docs/digital-twins.md) | Guide for implementing a new digital twin |
| [Sensors](docs/sensors.md) | Guide for implementing a new sensor |
| [Faults](docs/faults.md) | Guide for implementing fault models |
| [Scoring](docs/scoring.md) | Metrics, scoring policies, and leaderboard computation |
| [Contest Management](docs/contest-management.md) | Contest lifecycle, state machine, and submission rules |
| [Contest Authoring](docs/contest-authoring.md) | Configuration-driven contest creation guide |
| [Datasets](docs/datasets.md) | Client-side data collection and export |

---

## Development roadmap

### ✅ Phase 0 — Foundation
Core interfaces (`DigitalTwin`, `Sensor`, `FaultDescriptor`, `ScoringMetric`), plugin registries, configuration system, repository structure and documentation.

### ✅ Phase 1 — Minimal vertical slice
FastAPI backend, JWT authentication, mass-spring-damper twin, WebSocket streaming, contest lifecycle management (DRAFT → ACTIVE → CLOSED), real-time simulation engine.

### ✅ Phase 2 — Contest platform
Three-role system (ADMINISTRATOR, ORGANIZER, PARTICIPANT), two-phase contest model (observation → evaluation → submission), MAE scoring for forecasting tasks, automated leaderboards, deadline extension.

### ✅ Phase 3 — Advanced simulation
Sensor noise, drift, latency, quantization, saturation, outliers — fully configurable per sensor. Multiple simultaneous and intermittent faults with gradual physical effects.

### ✅ Phase 4 — Industrial twins
Industrial Pump, Electric Motor, Rotating Machinery, and Smart Building twins integrated with zero changes to EPIC Core, validating the extensibility architecture.

### ✅ Phase 5 — Educational ecosystem
`epic-elios-client` SDK on PyPI, Jupyter quickstart notebook, contest templates, twin catalog API, responsive single-page web frontend with role-based dashboards for all three roles, admin bootstrap, closed registration.

### 🔜 Phase 6 — Advanced contest types
Fault classification tasks, remaining useful life estimation, multi-task contests (combined forecasting + anomaly detection), public and private leaderboard separation.

### 🔜 Phase 7 — Research platform
Multi-agent simulations, federated learning challenges, reinforcement learning environments, digital twin benchmarking, large-scale distributed simulations.

---

## Powered by Elios Lab

EPIC is developed and maintained by [Elios Lab](https://www.elios.unige.it/) at the University of Genoa.

The long-term vision is a domain-independent framework where digital twins, sensors, fault models, and contest types are interchangeable building blocks — and where a new machine learning competition can be created entirely through configuration, while a new application domain can be introduced by implementing a small, well-defined set of interfaces.
