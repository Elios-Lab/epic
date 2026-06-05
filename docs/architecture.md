# EPIC Architecture

> Related: [Simulation Engine](simulation-engine.md) · [Domain Model](domain-model.md) · [Digital Twins](digital-twins.md) · [Sensors](sensors.md)

The platform is designed around one central principle:

> The competition infrastructure must be independent from the simulated domain.

Digital twins, sensors, and fault models implement well-defined interfaces. The EPIC Core orchestrates them without knowing anything about their domain logic.

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
                 +----------+----------+
                            |
                            v
                 +----------------------+
                 |    Contest Layer     |
                 +----------+----------+
                            |
                            v
                 +----------------------+
                 |   Simulation Engine  |
                 |    (EPIC Core)       |
                 +----------+----------+
                            |
              +-------------+-------------+
              |                           |
              v                           v
  +--------------------+     +--------------------+
  |   Digital Twin     |     |      Sensors       |
  |  (owns its faults) |     | (epic_sensors/)    |
  +--------------------+     +--------------------+
```

---

# Architectural Layers

## EPIC Core

Contains all domain-independent logic.

Responsibilities:

- simulation orchestration
- session lifecycle
- twin and sensor registration
- WebSocket broadcasting
- contest management
- scoring

The Core must not contain knowledge of any specific domain. It interacts with twins and sensors exclusively through the interfaces defined in `epic_core/interfaces.py`.

---

## Contest Layer

Manages machine learning competitions.

Responsibilities:

- contest lifecycle (DRAFT → SCHEDULED → ACTIVE → CLOSED → ARCHIVED)
- participant registration
- submission intake
- scoring and leaderboards

The Contest Layer never depends on a specific digital twin.

---

## Digital Twin Layer

A digital twin represents a simulated physical system. It is a self-contained unit responsible for:

- maintaining and evolving its internal latent state
- managing its own faults — activating them at the scheduled times and incorporating their effects directly into state evolution
- exposing metadata about available faults for contest configuration and API listing

Twins live in `epic_twins/`. Each twin is a Python package that implements the `DigitalTwin` interface.

**The twin is the only place where fault logic lives.** The engine never calls any fault method directly.

---

## Sensor Layer

Sensors live in `epic_sensors/` and are reusable across any twin that exposes the right physical quantity.

A sensor reads one physical quantity from the twin's state and produces a noisy, degraded measurement. The full degradation pipeline (noise, drift, latency, quantization, saturation, outliers) is internal to the sensor.

Sensors are completely independent from specific twins. The coupling is mediated exclusively by `PhysicalQuantity` — a sensor declares what it measures, a twin declares what quantities it provides. See [Physical Quantities](quantities.md).

---

# Simulation Flow

A simulation session is started automatically when a contest transitions to ACTIVE. The session runs in real wall-clock time until the contest closes.

```text
twin.configure(initial_conditions, fault_schedule)
      |
      v  returns initial state
      |
      +------------ simulation loop (wall-clock time) ------------------+
      |                                                                  |
      v                                                                  |
 twin.step(state, dt)                                                    |
      |                                                                  |
      |  ← twin manages fault activation and application internally      |
      |                                                                  |
      v                                                                  |
 sensor.observe(new_state, dt)   for each configured sensor             |
      |                                                                  |
      |  ← sensor applies its own degradation pipeline internally        |
      |                                                                  |
      v                                                                  |
 twin.get_active_faults()        for label generation only              |
      |                                                                  |
      v                                                                  |
 SensorObservation (sensors + labels)  → persisted privately            |
 WebSocket broadcast (sensors only)    → delivered to participants      |
      |                                                                  |
      +------------------------------------------------------------------+
```

The engine has no fault logic. It calls `twin.step()`, calls `sensor.observe()`, and calls `twin.get_active_faults()` solely to produce ground-truth labels for the scoring engine.

See [Simulation Engine](simulation-engine.md) for the full specification.

---

# Extension Model

New digital twins, sensors, and scoring metrics are added by implementing the interfaces in `epic_core/interfaces.py` and registering them at application startup.

```python
# epic_api/main.py  (startup)
from epic_core.registry import twin_registry, sensor_registry
from epic_twins.mechanical.twin import MechanicalTwin
from epic_sensors.linear.position import PositionSensor
from epic_sensors.linear.velocity import VelocitySensor

twin_registry.register(MechanicalTwin())
sensor_registry.register(PositionSensor())
sensor_registry.register(VelocitySensor())
```

No dynamic discovery framework is required. The API automatically exposes all registered twins and sensors. No Core modification is needed when a new twin or sensor is added.

**Faults are not registered globally.** They are owned by their twin and returned by `twin.get_faults()`. The engine and API load fault descriptors directly from the twin.

---

# Data Visibility

Participants receive only sensor readings, delivered through the WebSocket stream. Ground-truth labels, fault metadata, and the twin's internal state are always stored privately and never exposed through participant-facing API endpoints.

The scoring engine reads labels from the private store when evaluating submissions.

---

# Extensibility Requirement

The architecture must allow new digital twins, sensors, fault models, and scoring metrics to be integrated without modifying any EPIC Core file.

The test for this requirement: could a completely different domain (biomedical monitor, smart building, power grid) be integrated by implementing interfaces alone, with no changes to the Core, the Contest Layer, the REST API, or the WebSocket API?

If the answer is no, the proposed change must be reconsidered.
