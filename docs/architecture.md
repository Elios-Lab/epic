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
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |    Contest Layer     |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |   Simulation Engine  |
                 +----------+-----------+
                            |
              +-------------+-------------+
              |                           |
              v                           v
   +--------------------+      +--------------------+
   |   Digital Twin     |      |      Sensors       |
   +--------------------+      +--------------------+
```

---

# Architectural Layers

## EPIC Core

The EPIC Core contains all the domain-independent logic of the platform. It orchestrates simulations and manages the lifecycle of simulation sessions, holds the registries through which twins, sensors, and metrics are made available, fans sensor readings out to connected participants through the WebSocket broadcaster, and provides the building blocks for contest management and scoring.

The Core must not contain knowledge of any specific domain. It interacts with twins and sensors exclusively through the interfaces defined in `epic_core/interfaces.py`.

---

## Contest Layer

The Contest Layer manages machine learning competitions. It drives each contest through its lifecycle (DRAFT → SCHEDULED → ACTIVE → CLOSED → ARCHIVED), handles participant registration, receives and validates submissions, and computes scores and leaderboards from them.

The Contest Layer never depends on a specific digital twin.

---

## Digital Twin Layer

A digital twin represents a simulated physical system. It is a self-contained unit that maintains and evolves its internal latent state, manages its own faults — activating them at the scheduled times and incorporating their effects directly into state evolution — and exposes metadata about the faults it supports, so that contest configuration and API listing can discover them without knowing anything about the underlying physics.

Twins live in `epic_twins/`. Each twin is a Python package that implements the `DigitalTwin` interface. The five built-in twins are described in detail in the [Digital Twin Catalog](twin-catalog.md).

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

New digital twins, sensors, scoring metrics, and task types are added by implementing the interfaces in `epic_core/interfaces.py` (`DigitalTwin`, `Sensor`, `ScoringMetric`, `TaskEvaluator`) and registering them at application startup. Each built-in plugin package exposes a `register()` entry point that the API application calls in its lifespan hook:

```python
# epic_api/main.py  (startup)
from epic_sensors.plugin import register as register_sensors
from epic_twins.mass_spring_damper.plugin import register as register_mass_spring_damper

register_sensors()
register_mass_spring_damper()
```

A third-party twin follows exactly the same pattern, registering its instance directly:

```python
import epic_core.registry as registry_module
from my_package import MyTwin

registry_module.twin_registry.register(MyTwin())
```

No dynamic discovery framework is required. The API automatically exposes all registered twins and sensors. No Core modification is needed when a new twin or sensor is added.

**Faults are not registered globally.** They are owned by their twin and returned by `twin.get_faults()`. The engine and API load fault descriptors directly from the twin.

---

# Data Visibility

Participants receive only sensor readings, delivered through the WebSocket stream. Ground-truth labels, fault metadata, and the twin's internal state are always stored privately and never exposed through participant-facing API endpoints.

The scoring engine reads labels from the private store when evaluating submissions.

---

# Extensibility Requirement

The architecture must allow new digital twins, sensors, fault models, scoring metrics, and contest task types to be integrated without modifying any EPIC Core file.

The test for this requirement: could a completely different domain (biomedical monitor, smart building, power grid) be integrated by implementing interfaces alone, with no changes to the Core, the Contest Layer, the REST API, or the WebSocket API?

If the answer is no, the proposed change must be reconsidered.
