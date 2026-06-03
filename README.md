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

- Plugin-based architecture
- Domain-independent design
- Multiple digital twins
- Scenario management
- Fault injection

### Dataset Generation

- Historical data generation
- Configurable scenarios
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

├── epic_core/
├── epic_api/
├── epic_auth/
├── epic_contests/
├── epic_twins/
├── epic_sensors/
├── epic_faults/
├── epic_scoring/
├── epic_storage/
├── docs/
└── tests/
```

---

## Documentation

Detailed documentation is available in the `docs/` directory.

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | High-level system architecture and layers |
| [Domain Model](docs/domain-model.md) | Canonical entity definitions and database schema |
| [Plugin System](docs/plugin-system.md) | Canonical interface definitions for all plugin types |
| [Plugin Registry](docs/plugin-registry.md) | Registry specification, discovery, and versioning |
| [Simulation Engine](docs/simulation-engine.md) | Simulation loop, concurrency, WebSocket streaming |
| [API Specification](docs/api-specification.md) | REST and WebSocket API reference |
| [Authentication](docs/authentication.md) | Auth, JWT, and role-based access control |
| [Configuration](docs/configuration.md) | Environment variables and settings reference |
| [Error Handling](docs/error-handling.md) | Exception hierarchy and API error mapping |
| [Testing](docs/testing.md) | Testing strategy, utilities, and contract tests |
| [Digital Twins](docs/digital-twins.md) | Guide for implementing digital twin plugins |
| [Sensors](docs/sensors.md) | Guide for implementing sensor plugins |
| [Faults](docs/faults.md) | Guide for implementing fault plugins |
| [Scoring](docs/scoring.md) | Metrics, scoring policies and leaderboards |
| [Contest Management](docs/contest-management.md) | Contest lifecycle, submissions and rankings |
| [Contest Authoring](docs/contest-authoring.md) | Configuration-driven contest creation guide |
| [Datasets](docs/datasets.md) | Dataset generation and export |

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

Create a twin by implementing the `DigitalTwin` interface (see [Digital Twins](docs/digital-twins.md) and [Plugin System](docs/plugin-system.md)), then register it in your application startup:

```python
from epic_core.registry import twin_registry
from my_twins import MechanicalTwin

twin_registry.register(MechanicalTwin())
```

No API changes are required. The new twin will appear automatically at `GET /api/v1/twins`.

---

# Development Roadmap

The development of EPIC will follow an incremental approach.

The primary objective is not simulation realism, but architectural validation and extensibility.

Each phase should produce a fully working system before increasing complexity.

---

## Phase 0 – Foundation

Goal: Build the minimal EPIC infrastructure.

Deliverables:

- Repository structure
- Documentation
- Core interfaces
- Plugin registries
- Configuration system
- Development environment
- CI/CD setup

Success criteria:

- The platform can discover plugins.
- The architecture is stable enough to support future extensions.

---

## Phase 1 – Minimal Vertical Slice

Goal: Create a complete end-to-end workflow using a simple digital twin.

Deliverables:

- FastAPI backend
- Mechanical digital twin
- Position sensor
- Velocity sensor
- Temperature sensor
- One normal scenario
- One fault scenario
- Simulation sessions
- WebSocket streaming
- Dataset export
- Basic forecasting score

Success criteria:

- A participant can create a simulation session.
- A participant can stream sensor data.
- A participant can generate a dataset.
- A participant can submit a forecasting solution.

---

## Phase 2 – Contest Platform

Goal: Introduce contest management capabilities.

Deliverables:

- User management
- Authentication
- Contest creation
- Contest lifecycle management
- Contest registration
- Submission management
- Leaderboards
- Score persistence

Success criteria:

- Multiple users can participate in competitions.
- Leaderboards update automatically.
- Contest deadlines are enforced.

---

## Phase 3 – Advanced Simulation

Goal: Improve realism and simulation richness.

Deliverables:

- Advanced sensor models
- Sensor drift
- Quantization
- Latency
- Fault scheduling
- Multiple simultaneous faults
- Scenario composition

Success criteria:

- Realistic forecasting and anomaly detection tasks become possible.

---

## Phase 4 – Industrial Twins

Goal: Introduce realistic industrial systems.

Candidate twins:

- Industrial Pump
- Electric Motor
- Rotating Machinery
- Smart Building

Candidate sensors:

- Pressure
- Flow
- Current
- Voltage
- Vibration

Success criteria:

- EPIC supports industrial predictive maintenance challenges.

---

## Phase 5 – Advanced Contest Types

Goal: Support more sophisticated machine learning competitions.

Deliverables:

- Fault classification tasks
- Remaining Useful Life estimation
- Multi-task contests
- Hidden evaluation datasets
- Public and private leaderboards

Success criteria:

- EPIC supports research-grade competitions.

---

## Phase 6 – Educational Ecosystem

Goal: Make EPIC usable by instructors without software development.

Deliverables:

- Contest templates
- Web-based contest authoring
- Twin catalog
- Dataset generation wizard
- Educational dashboards

Success criteria:

- A professor can create a complete contest through configuration alone.

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

- New research domains can be integrated as plugins without modifying the EPIC Core.

---

# Long-Term Vision

EPIC should evolve into a domain-independent framework for simulation-driven machine learning competitions.

Digital twins, sensors, fault models and contest types should become interchangeable building blocks.

The ultimate measure of success is architectural flexibility:

A new machine learning competition should be creatable primarily through configuration, while a new application domain should be introducible by implementing a small set of well-defined interfaces.