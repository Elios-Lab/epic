# EPIC Architecture

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

Each plugin type has its own registry.

```python
registry.register(MyTwin())
sensor_registry.register(TemperatureSensor)
fault_registry.register(BiasFault)
```

The API automatically exposes registered components.

No modification to the Core should be required.

---

# Simulation Flow

A simulation session follows these steps:

1. Load digital twin
2. Load scenario
3. Initialize latent state
4. Advance simulation
5. Apply faults
6. Generate sensor observations
7. Stream observations
8. Store history

```text
Latent State
      |
      v
 State Evolution
      |
      v
 Fault Injection
      |
      v
 Sensor Observation
      |
      v
 API Stream
```

---

# Data Visibility

Different contest modes expose different information.

## Training Mode

Can expose:

- sensor readings
- labels
- fault metadata
- latent state (optional)

## Validation Mode

Typically exposes:

- sensor readings

May expose limited labels.

## Test Mode

Exposes:

- sensor readings only

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