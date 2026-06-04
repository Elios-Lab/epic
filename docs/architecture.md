# EPIC Architecture

> Related: [Plugin System](plugin-system.md) · [Plugin Registry](plugin-registry.md) · [Simulation Engine](simulation-engine.md) · [Domain Model](domain-model.md)

The platform is designed around a central principle:

> The competition infrastructure must be independent from the simulated domain.

Digital twins, sensors, fault models and scenarios are treated as plugins.

The EPIC Core provides orchestration, contest management, evaluation and data streaming.

---

# High-Level Architecture

```text
                    +----------------+
                    |   Web Clients  |
                    +-------+--------+
                            |
                            v
                 +----------------------+
                 |      REST API        |
                 |    WebSocket API     |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |    Contest Layer     |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |      EPIC Core       |
                 +----------+-----------+
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
+---------------+ +---------------+ +---------------+
| Twin Registry | |Sensor Registry| |Fault Registry |
+---------------+ +---------------+ +---------------+
        |
        v
+--------------------------------------+
|        Digital Twin Plugins          |
+--------------------------------------+
```

---

# Architectural Layers

The system is divided into several layers.

## EPIC Core

The Core contains all domain-independent logic.

Responsibilities:

- simulation orchestration
- session lifecycle
- registry management
- scheduling
- clock management
- plugin discovery

The Core must not know anything about:

- pumps
- motors
- batteries
- buildings
- biomedical systems

The Core only interacts through interfaces.

---

## Contest Layer

The Contest Layer manages competitions.

Responsibilities:

- contest lifecycle
- registrations
- submissions
- scoring
- rankings
- leaderboards

The Contest Layer should not depend on any specific digital twin.

---

## Digital Twin Layer

Digital twins implement simulated systems.

Examples:

- Mechanical System
- Industrial Pump
- Electric Motor
- Smart Building
- Power Grid

A digital twin contains:

- latent state
- dynamics
- sensors
- faults
- scenarios

---

## Sensor Layer

Sensors transform latent state variables into measurements.

Sensors are reusable components.

Examples:

- TemperatureSensor
- PressureSensor
- VibrationSensor
- PositionSensor

---

## Fault Layer

Faults introduce anomalies.

Faults are reusable and independent.

Examples:

- BiasFault
- DriftFault
- IncreasedFrictionFault
- PacketLossFault

---

# Plugin Architecture

The EPIC Core discovers plugins through registries.

Each plugin type has its own registry. Registries are module-level singletons in `epic_core/registry.py`, populated at application startup.

```python
twin_registry.register(MechanicalTwin())
sensor_registry.register(TemperatureSensor())
fault_registry.register(SensorBiasFault())
```

The API automatically exposes all registered components. No modification to the Core is required when new plugins are added.

See [Plugin Registry](plugin-registry.md) for the full specification of registration, auto-discovery, versioning, and lookup.

---

# Simulation Flow

A simulation session is executed by the `SimulationEngine`, an asyncio-based component in the EPIC Core.

Each contest has exactly one simulation session, started automatically when the contest becomes ACTIVE and running in real wall-clock time until the contest closes.

High-level flow:

1. Contest transitions to ACTIVE → platform creates and starts the session
2. Load twin and scenario from registries
3. Initialise latent state
4. Loop (wall-clock time): advance state → apply faults → observe sensors → persist privately → broadcast to WebSocket subscribers
5. Contest transitions to CLOSED → session stops, status set to COMPLETED

```text
Latent State
      |
      v
 twin.step()                         ← state evolution (returns new state)
      |
      v
 fault.apply()                       ← StateFault and ParameterFault
      |
      v
 sensor.observe()                    ← produces raw measurement
      |
      v
 sensor_fault.apply_to_measurement() ← SensorFault
      |
      v
 SensorObservation (with labels)     ← persisted privately for scoring
      |
      v
 WebSocket broadcast (sensors only)  ← delivered to all connected participants
```

See [Simulation Engine](simulation-engine.md) for the full engine specification including wall-clock timing, WebSocket broadcasting, and label storage.

---

# Data Visibility

In Phase 1, data visibility is fixed: participants always receive sensor readings only through the WebSocket stream. Labels, fault metadata, and latent state are always stored privately and never exposed to participants.

Future phases may introduce configurable visibility modes (e.g. a training contest that exposes labels to help students learn). The three intended modes are:

## Training Mode (future)

May expose sensor readings plus labels and fault metadata, configurable per contest.

## Validation Mode (future)

Exposes sensor readings only, possibly with partial labels.

## Test Mode (future)

Exposes sensor readings only. No hidden information available.

No internal state information.

---

# Extensibility Requirements

The architecture must allow:

- new digital twins
- new sensors
- new fault models
- new scoring metrics
- new contest types

without changing:

- EPIC Core
- Contest Layer
- REST API
- WebSocket API

---

# Long-Term Goal

EPIC should become a generic framework for simulation-driven machine learning competitions.

The first mechanical twin is only a proof of concept.

Future domains should be integrated by implementing interfaces rather than modifying infrastructure.