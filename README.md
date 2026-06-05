# EPIC - ELIOS Predictive Intelligence Challenge

> A simulation-driven machine learning competition platform based on extensible digital twins, streaming sensor data, forecasting, anomaly detection and predictive maintenance.

## Overview

EPIC (ELIOS Predictive Intelligence Challenge) is a framework for creating machine learning competitions based on simulated environments and digital twins. Unlike traditional competitions that provide static datasets, EPIC allows participants to interact with digital twins through APIs and real-time streams, generate their own datasets, train models and submit solutions.

The platform is designed for:

- Education
- Research
- Benchmarking
- Industrial AI experimentation

Supported tasks include:

- Time Series Forecasting
- Anomaly Detection
- Fault Diagnosis
- Predictive Maintenance
- Prognostics
- Remaining Useful Life Estimation

---

## Core Idea

EPIC is not a simulator.

EPIC is not a digital twin.

EPIC is a competition framework that uses digital twins to generate machine learning challenges.

The architecture separates:

- Competition management
- Simulation infrastructure
- Digital twin implementations

This allows new digital twins, sensors and fault models to be added without modifying the platform core.

---

## Main Features

### Competition Management

- Multiple simultaneous contests
- Contest scheduling
- User registration
- Leaderboards
- Automatic evaluation
- Submission management

### Digital Twin Framework

- Interface-driven, domain-independent design
- Multiple digital twins with self-contained fault management
- Fault injection via contest configuration (start time, end time, severity)
- Reusable sensors decoupled from specific twins via physical quantity ontology

### Dataset Generation

- Historical data generation
- Configurable fault schedules and initial conditions
- Multiple seeds
- Export to CSV and JSONL

### Streaming Infrastructure

- WebSocket sensor streams
- Real-time simulation
- Configurable sampling rates

### Evaluation Framework

- Forecasting metrics
- Anomaly detection metrics
- Custom scoring policies

---

## Architecture

EPIC consists of:

- EPIC Core
- Digital Twin Framework
- Sensor Framework
- Fault Framework
- Contest Framework
- Dataset Generation Framework
- Scoring Framework
- REST API Layer
- WebSocket Layer
- Authentication Layer

---

## First Digital Twin

The first implementation intentionally uses a very simple mechanical system.

Examples:

- Mass-Spring-Damper System
- Rotational Inertia System

The objective is to validate the architecture before introducing more realistic industrial systems.

Future twins may include:

- Industrial pumps
- Electric motors
- Smart buildings
- Energy systems
- Biomedical systems
- Network systems

---

## Repository Structure

```text
epic/
├── epic_core/              ← interfaces, registry, engine, broadcaster, db models, auth
│   ├── db/                 ← SQLAlchemy models and session management
│   └── quantities.py       ← PhysicalQuantity ontology (shared by sensors and twins)
├── epic_api/               ← FastAPI application, routers, dependencies, error handling
│   └── routers/            ← twins, sensors, auth, users, contests, registrations, submissions, ws
├── epic_twins/             ← digital twins (self-contained state, dynamics, fault management)
│   ├── mass_spring_damper/ ← mechanical system
│   ├── industrial_pump/    ← centrifugal pump
│   ├── electric_motor/     ← three-phase induction motor
│   ├── rotating_machinery/ ← shaft and gearbox
│   └── smart_building/     ← commercial building floor with HVAC
├── epic_sensors/           ← sensors (independent of twins, reusable across domains)
├── alembic/                ← database migrations
│   └── versions/
├── docs/                   ← architecture and API documentation
└── tests/                  ← unit, integration, and API tests
    ├── core/
    ├── api/
    ├── twins/
    └── sensors/
```

---

## Documentation

Detailed documentation is available in the `docs/` directory.

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | High-level system architecture and layers |
| [Domain Model](docs/domain-model.md) | Canonical entity definitions and database schema |
| [Physical Quantities](docs/quantities.md) | Ontology shared between sensors and digital twins |
| [Simulation Engine](docs/simulation-engine.md) | Simulation loop, concurrency, WebSocket streaming |
| [API Specification](docs/api-specification.md) | REST and WebSocket API reference |
| [Authentication](docs/authentication.md) | Auth, JWT, and role-based access control |
| [Configuration](docs/configuration.md) | Environment variables and settings reference |
| [Error Handling](docs/error-handling.md) | Exception hierarchy and API error mapping |
| [Testing](docs/testing.md) | Testing strategy, utilities, and contract tests |
| [Digital Twins](docs/digital-twins.md) | Guide for implementing digital twins |
| [Sensors](docs/sensors.md) | Guide for implementing sensors |
| [Faults](docs/faults.md) | Guide for implementing fault models |
| [Scoring](docs/scoring.md) | Metrics, scoring policies and leaderboards |
| [Contest Management](docs/contest-management.md) | Contest lifecycle, submissions and rankings |
| [Contest Authoring](docs/contest-authoring.md) | Configuration-driven contest creation guide |
| [Datasets](docs/datasets.md) | Client-side data collection via WebSocket |

---

## Getting Started

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Install

```bash
git clone https://github.com/your-org/epic.git
cd epic
uv sync
```

### Run the development server

```bash
uv run uvicorn epic_api.main:app --reload
```

The API will be available at `http://localhost:8000`.

Interactive documentation is auto-generated at:

- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:8000/redoc` (ReDoc)

### Run tests

```bash
uv run pytest
```

### Register a digital twin

Create a twin by implementing the `DigitalTwin` interface (see [Digital Twins](docs/digital-twins.md)), then register it in your application startup:

```python
from epic_core.registry import twin_registry
from my_twins import MechanicalTwin

twin_registry.register(MechanicalTwin())
```

No API changes are required. The new twin will appear automatically at `GET /api/v1/twins`.

---

# Development Roadmap

The development of EPIC follows an incremental approach.

The primary objective is not simulation realism, but architectural validation and extensibility.

Each phase produces a fully working system before increasing complexity.

---

## Phase 0 – Foundation ✅

Goal: Build the minimal EPIC infrastructure.

Deliverables:

- Repository structure ✅
- Documentation ✅
- Core interfaces (`DigitalTwin`, `Sensor`, `FaultDescriptor`, `ScoringMetric`) ✅
- Registries for twins, sensors, and scoring metrics ✅
- Configuration system ✅
- Development environment ✅

Success criteria:

- The platform can register and look up twins and sensors. ✅
- The architecture is stable enough to support future extensions. ✅

---

## Phase 1 – Minimal Vertical Slice ✅

Goal: Create a complete end-to-end workflow using a simple digital twin running in real time.

Deliverables:

- FastAPI backend ✅
- User management and JWT authentication ✅
- Mass-spring-damper digital twin with self-contained fault management ✅
- Position, velocity, acceleration, temperature sensors ✅
- Fault injection via contest fault schedule (fault ID, start time, end time, severity) ✅
- Contest lifecycle management (DRAFT → ACTIVE → CLOSED) ✅
- Shared real-time simulation per contest (wall-clock time) ✅
- WebSocket streaming of live sensor readings to participants ✅
- Private server-side observation storage for scoring ✅

Success criteria:

- An admin can create and activate a contest with a specific fault schedule. ✅
- Participants can connect via WebSocket and receive live sensor readings. ✅
- The simulation runs in real wall-clock time and stops when the contest closes. ✅

---

## Phase 2 – Contest Platform ✅

Goal: Enable participants to compete and be evaluated.

Deliverables:

- Three-role system: ADMINISTRATOR, ORGANIZER, PARTICIPANT ✅
- Contest registration (participants join SCHEDULED or ACTIVE contests) ✅
- Submission management with temporal integrity anchor (`prediction_from_sequence`) ✅
- MAE scoring for forecasting tasks, F1 scoring for anomaly detection tasks ✅
- Leaderboards with automatic ranking after each scored submission ✅
- Deadline extension for organizers and admins ✅

Success criteria:

- Multiple users can participate in competitions. ✅
- Leaderboards update automatically after submissions. ✅
- Submissions are verified as temporally honest (not post-hoc). ✅

---

## Phase 3 – Advanced Simulation ✅

Goal: Improve realism and simulation richness.

Deliverables:

- Sensor noise, drift, latency, quantization, saturation, false readings, outliers ✅
- Sensor pipeline fully configurable per sensor in `contest.sensor_configs` ✅
- Multiple simultaneous faults via fault schedule ✅
- Gradual fault effects (physical state evolves at each step) ✅
- Intermittent faults (multiple schedule entries with `end_time`) ✅

Deferred:

- Dynamic severity ramp-up within the twin (e.g. exponential degradation curves)
- Additional fault types for the mass-spring-damper twin

Success criteria:

- Realistic anomaly detection and forecasting challenges are possible. ✅
- A student cannot trivially distinguish sensor noise from a genuine fault. ✅

---

## Phase 4 – Industrial Twins ✅

Goal: Introduce realistic industrial systems.

Twins:

- Industrial Pump (flow, pressure, vibration, temperature) ✅
- Electric Motor (current, voltage, RPM, temperature) ✅
- Rotating Machinery (vibration, power, speed, temperature) ✅
- Smart Building (temperature, humidity, CO2, occupancy) ✅

Sensors and physical quantities added:

- `FLOW_RATE`, `PRESSURE`, `VIBRATION`, `CURRENT`, `VOLTAGE`, `ROTATIONAL_SPEED`, `POWER`, `CO2_CONCENTRATION`, `OCCUPANCY` ✅

Architecture validation:

- All four twins integrated with zero changes to EPIC Core ✅
- Each contest gets its own independent twin instance — concurrent contests with the same twin type are fully isolated ✅
- One shared simulation per contest — all participants in a contest receive the same real-time sensor stream ✅

Success criteria:

- EPIC supports industrial predictive maintenance challenges. ✅
- A new twin can be integrated by implementing `DigitalTwin` alone, with no Core changes. ✅

---

## Phase 5 – Educational Ecosystem

Goal: Make EPIC usable by instructors and researchers without software development.

Deliverables:

- Contest templates with predefined fault schedules and sensor configurations
- Web-based contest authoring UI
- Twin catalog with browsable fault and sensor documentation
- WebSocket client starter kit (Python + Jupyter)
- Educational dashboards (live simulation visualization)

Success criteria:

- A professor can create a complete contest through configuration alone, without writing code.

---

## Phase 6 – Advanced Contest Types

Goal: Support more sophisticated machine learning competitions.

Deliverables:

- Fault classification tasks (predict which fault, not just anomaly/normal)
- Remaining Useful Life estimation
- Multi-task contests (combined forecasting + anomaly detection scoring)
- Hidden evaluation datasets
- Public and private leaderboards

Success criteria:

- EPIC supports research-grade competitions.

---

## Phase 7 – Research Platform

Goal: Transform EPIC into a general-purpose research framework.

Possible extensions:

- Multi-agent simulations
- Federated learning challenges
- Reinforcement learning environments
- Digital twin benchmarking
- Large-scale distributed simulations

Success criteria:

- New research domains can be integrated by implementing interfaces alone, without modifying the EPIC Core.

---

# Long-Term Vision

EPIC should evolve into a domain-independent framework for simulation-driven machine learning competitions.

Digital twins, sensors, fault models and contest types should become interchangeable building blocks.

The ultimate measure of success is architectural flexibility: a new machine learning competition should be creatable primarily through configuration, while a new application domain should be introducible by implementing a small set of well-defined interfaces.