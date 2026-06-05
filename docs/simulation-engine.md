# Simulation Engine

> Related: [Digital Twins](digital-twins.md) · [Sensors](sensors.md) · [API Specification](api-specification.md)

The Simulation Engine is the EPIC Core component responsible for running digital twin simulations, collecting sensor observations, and delivering results to participants.

The engine is domain-independent. It interacts with the twin exclusively through the `DigitalTwin` interface and with sensors through the `Sensor` interface. It has no knowledge of fault logic, physical quantities, or domain-specific behaviour.

---

# Responsibilities

The engine is responsible for:

- managing the simulation loop
- calling `twin.configure()` once at session start
- calling `twin.step()` at each time step
- calling `sensor.observe()` for each configured sensor
- collecting ground-truth labels via `twin.get_active_faults()`
- persisting observations privately for scoring
- broadcasting sensor readings to WebSocket subscribers
- managing session status transitions

The engine is not responsible for:

- fault activation or application (the twin manages this)
- contest management
- submission evaluation
- authentication
- API routing

---

# Execution Model

Each contest has exactly one simulation session. It starts when the contest transitions to ACTIVE and runs in real wall-clock time until the contest transitions to CLOSED.

The engine runs the session continuously at `sampling_rate_hz`. Every observation is:

1. Persisted to the database with full labels (private, for scoring only).
2. Broadcast to all connected WebSocket clients (sensor readings only, no labels).

There is no batch mode, no accelerated simulation, and no pause mechanism available to participants.

---

# Concurrency Model

The engine uses Python `asyncio`. Each session runs as an independent `asyncio.Task`. Multiple sessions can run concurrently in the same process.

If `twin.step()` is computationally intensive it must be offloaded to a thread pool to avoid blocking the event loop:

```python
loop = asyncio.get_running_loop()
new_state = await loop.run_in_executor(None, twin.step, state, dt)
```

---

# SimulationEngine Interface

```python
class SimulationEngine:

    async def run_session(self, session_id: str, db_factory) -> None:
        """
        Execute a contest simulation session to completion.

        Runs in real wall-clock time at session.sampling_rate_hz.
        Each observation is persisted privately and broadcast to all
        WebSocket subscribers of the contest.

        The session ends naturally when wall-clock time reaches
        contest.end_date.

        Raises PluginExecutionError if the twin raises an unrecoverable
        exception during configure() or step().
        """
        pass
```

---

# Session Lifecycle

```text
CREATED
    ↓  (engine starts the loop)
RUNNING
    ↓  (wall-clock reaches contest.end_date)
COMPLETED

    or

    ↓  (unrecoverable exception in twin.step() or sensor.observe())
FAILED
```

The engine updates session status in storage at each transition.

---

# Simulation Loop

```text
1.  Load twin from registry using contest.twin_id.

2.  Instantiate sensors from contest.sensor_configs with parameter overrides.
    Validate: sensor.measured_quantity ∈ twin.supported_quantities() for each sensor.
    Raise EPICValidationError if any sensor is incompatible.

3.  Call twin.configure(contest.initial_conditions, contest.fault_schedule) → state.
    Validate: every fault_id in contest.fault_schedule is in twin.get_faults().
    Raise EPICValidationError if any fault_id is unknown.

4.  Set session status to RUNNING.

5.  t = 0.0

6.  While wall-clock time < contest.end_date:

        a.  new_state = twin.step(state, dt)
            ← twin handles fault activation and application internally

        b.  For each sensor in contest_sensors:
                measurement = sensor.observe(new_state, dt)
                ← sensor applies its own degradation pipeline

        c.  active_faults = twin.get_active_faults()
            labels = {
                "is_anomaly": len(active_faults) > 0,
                "fault_ids":  [f["fault_id"]  for f in active_faults],
                "severities": {f["fault_id"]: f["severity"] for f in active_faults},
            }

        d.  Persist SensorObservation (sensors + labels) to database privately.

        e.  Broadcast { timestamp, session_id, sequence_id, sensors } to WebSocket.

        f.  Sleep dt seconds (wall-clock alignment).

        g.  state = new_state

7.  Set session status to COMPLETED.
```

Step 6a is the only place the engine interacts with the twin during the loop. The engine has no fault schedule, no fault objects, and no activation logic of its own.

---

# Session Configuration

The engine reads its configuration from the `Contest` and `SimulationSession` records:

```python
contest.twin_id            # which twin to load
contest.sensor_configs     # sensors + parameter overrides
contest.fault_schedule     # passed as-is to twin.configure()
contest.initial_conditions # passed as-is to twin.configure()
contest.end_date           # loop termination condition
session.sampling_rate_hz   # dt = 1 / sampling_rate_hz
session.seed               # optional RNG seed
```

---

# WebSocket Broadcasting

The message sent to participants contains sensor readings only. Labels are never included.

```json
{
  "timestamp": "2027-01-15T10:00:00.500Z",
  "session_id": "abc123",
  "sequence_id": 500,
  "sensors": {
    "position": 0.15,
    "velocity": 1.82,
    "temperature": 31.5
  }
}
```

Each client has its own bounded output queue. If a client is too slow to consume messages, its oldest messages are dropped. The engine's main loop is never blocked by slow clients.

---

# Reproducibility

If `session.seed` is set, the engine seeds the random number generators before starting the loop:

```python
import random, numpy as np
random.seed(session.seed)
np.random.seed(session.seed)
```

Twins and sensors must use module-level random functions to benefit from seeding.

---

# Error Handling

If `twin.step()` or `sensor.observe()` raises an exception, the engine sets session status to `FAILED`, stores the error message in `session.metadata["error"]`, and cancels the asyncio task.

Plugin exceptions are never propagated to the API layer. See [Error Handling](error-handling.md).

---

# Design Requirement

The engine must be fully testable without a real digital twin or sensor. `epic_core/testing.py` provides `MockTwin` and `MockSensor` for this purpose. See [Testing](testing.md).
