# Simulation Engine

> Related: [Plugin System](plugin-system.md) — interfaces · [Plugin Registry](plugin-registry.md) — registry · [API Specification](api-specification.md) — session endpoints

The Simulation Engine is the component of the EPIC Core responsible for running digital twin simulations, applying faults, collecting sensor observations, and delivering results to callers.

The engine is domain-independent. It interacts exclusively with the `DigitalTwin`, `Sensor`, `Fault`, and `Scenario` interfaces defined in [Plugin System](plugin-system.md).

---

# Responsibilities

The engine is responsible for:

- managing the simulation loop
- calling `twin.step()` at each time step
- applying active faults according to the fault schedule
- collecting sensor observations
- applying sensor faults to measurements
- pushing observations to the session output stream
- persisting observations to storage
- enforcing session duration and status transitions

The engine is not responsible for:

- contest management
- submission evaluation
- authentication
- API routing

---

# Execution Modes

The engine supports two execution modes.

## Streaming Mode

The simulation runs in real time (or near-real time).

Observations are pushed to a WebSocket stream as they are produced.

Used when a participant is interacting live with a session.

## Batch Mode

The simulation runs as fast as possible, without real-time constraints.

Observations are written directly to storage and optionally exported as a dataset.

Used for dataset generation.

---

# Concurrency Model

The engine uses Python's `asyncio`.

Each simulation session runs as an independent `asyncio.Task`.

Multiple sessions can run concurrently within the same process.

The engine must never block the event loop during a simulation step. If a twin's `step()` is computationally intensive, it must be offloaded to a thread pool:

```python
loop = asyncio.get_running_loop()
state = await loop.run_in_executor(executor, twin.step, state, dt)
```

---

# SimulationEngine Interface

The engine exposes the following interface to the rest of the Core:

```python
class SimulationEngine:

    async def run_session(self, session: SimulationSession) -> None:
        """
        Execute a simulation session.

        In streaming mode, observations are pushed to the session's
        output queue as they are produced.

        In batch mode, observations are written directly to storage.

        Raises SimulationError if the twin or scenario cannot be loaded,
        or if a fatal error occurs during the simulation loop.
        """
        pass

    def cancel_session(self, session_id: str) -> None:
        """
        Cancel a running session.

        The session status is set to CANCELLED.
        Any observations produced before cancellation are preserved.
        """
        pass

    def get_session_status(self, session_id: str) -> SessionStatus:
        pass
```

---

# Session Lifecycle

A session transitions through the following states:

```text
CREATED
    ↓
RUNNING
    ↓  (normal completion)
COMPLETED

    or

    ↓  (exception in twin or sensor)
FAILED

    or

    ↓  (cancel_session called)
CANCELLED
```

The engine is responsible for updating session status in storage at each transition.

---

# Simulation Loop

The engine executes the following loop for every session:

```text
1.  Load twin from registry
2.  Load scenario from twin
3.  Call scenario.initialize() → config dict
4.  Call twin.create_initial_state(config['initial_conditions']) → state
5.  Parse fault schedule from scenario.get_fault_schedule()
6.  Set session status to RUNNING
7.  t = 0.0
8.  While t < duration:
        a.  Advance time: t += dt  (dt = 1 / sampling_rate_hz)
        b.  Activate/deactivate faults according to schedule
        c.  Call twin.step(state, dt) → new_state
        d.  Call fault.apply(new_state, dt) for each active non-SensorFault
            (faults modify new_state in place)
        e.  For each sensor in twin.get_sensors():
                raw = sensor.observe(new_state)
                For each active SensorFault targeting this sensor:
                    raw = sensor_fault.apply_to_measurement(raw)
        f.  Assemble SensorObservation
        g.  Attach labels if session mode is TRAINING
        h.  Persist observation
        i.  Push observation to output stream (streaming mode only)
        j.  state = new_state
9.  Set session status to COMPLETED
```

---

# Fault Scheduling

The engine reads the fault schedule returned by `scenario.get_fault_schedule()` once at session start.

Each schedule entry has the form:

```python
{
    "fault_id": "sensor_bias",
    "start_time": 120.0,
    "end_time": None,       # None = active until session ends
    "severity": 0.5
}
```

At each time step, the engine checks which faults should be activated or deactivated:

```python
for entry in fault_schedule:
    fault = fault_registry.get(entry["fault_id"])

    if t >= entry["start_time"] and not fault_is_active:
        fault.activate(entry["severity"])

    if entry["end_time"] is not None and t >= entry["end_time"] and fault_is_active:
        fault.deactivate()
```

---

# SensorFault Targeting

A `SensorFault` must declare which sensor(s) it targets.

This is expressed through an additional required property on `SensorFault`:

```python
class SensorFault(Fault):

    @property
    @abstractmethod
    def target_sensor_ids(self) -> list[str]:
        """
        Return the sensor_ids this fault applies to.
        Return an empty list to apply to all sensors of the twin.
        """
        pass
```

The engine applies the fault only to matching sensors.

---

# Labels

In `TRAINING` mode, the engine attaches labels to each observation.

Labels are produced from the active fault state at that time step:

```python
labels = {
    "is_anomaly": len(active_faults) > 0,
    "fault_ids": [f.fault_id for f in active_faults],
    "severities": {f.fault_id: f.current_severity for f in active_faults},
}
```

In `VALIDATION` and `TEST` modes, labels are stored in the database but are not included in the observation payload returned by the API.

---

# WebSocket Streaming

In streaming mode, the engine pushes each `SensorObservation` to an `asyncio.Queue` associated with the session.

The WebSocket handler reads from this queue and forwards to the connected client:

```text
SimulationEngine
      ↓  (asyncio.Queue.put)
SessionQueue
      ↓  (asyncio.Queue.get)
WebSocketHandler
      ↓  (WebSocket.send_json)
Client
```

The queue has a bounded capacity. If the client is too slow to consume observations, the engine drops the oldest entry and continues. Dropped observations are still persisted to storage.

---

# Simulation Clock

The engine uses a virtual clock, not wall-clock time.

In streaming mode, the engine sleeps for `dt` seconds between steps to approximate real-time delivery.

In batch mode, there is no sleep — steps execute as fast as possible.

The virtual time `t` is what is stored in `SensorObservation.timestamp`, not the wall-clock time of observation production. This guarantees reproducibility.

---

# Reproducibility

If `session.seed` is set, the engine seeds the random number generator before the simulation loop:

```python
import random
import numpy as np

random.seed(session.seed)
np.random.seed(session.seed)
```

Twins and sensors must use the module-level random functions (not private RNG instances) to benefit from this seeding.

---

# Error Handling

If `twin.step()` raises an exception, the engine:

1. Logs the exception.
2. Sets session status to `FAILED`.
3. Stores the error message in `session.metadata["error"]`.
4. Cancels the session's asyncio Task.

The same policy applies to `sensor.observe()` and `fault.apply()`.

The engine must never propagate a plugin exception to the API layer uncaught. See [Error Handling](error-handling.md) for the full exception hierarchy.

---

# Dataset Generation

Dataset generation is batch execution of multiple sessions.

The engine runs each session sequentially or concurrently (configurable) and writes all observations to storage.

When all sessions complete, the storage layer exports the observations to the requested format (CSV, JSONL).

The engine does not manage export format — it only runs sessions. The dataset service coordinates the full pipeline.

---

# Design Requirement

The simulation engine must be fully testable without a real digital twin.

The Core must provide a `MockTwin` and `MockScenario` for use in unit tests of the engine itself.

See [Testing](testing.md) for details.
