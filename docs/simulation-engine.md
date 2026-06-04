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

# Execution Model

Each contest has exactly one simulation session, running in real wall-clock time from the moment the contest becomes ACTIVE until it becomes CLOSED.

The engine runs this session continuously at the configured `sampling_rate_hz`. Every produced observation is:

1. Pushed to all connected WebSocket clients (participants receive sensor readings only).
2. Persisted to the database privately with full labels (for scoring use only).

There is no batch mode, no accelerated simulation, and no pause or stop mechanism available to participants. The simulation clock is wall-clock time.

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

    async def run_session(
        self,
        session_id: str,
        db_factory,
    ) -> None:
        """
        Execute a contest simulation session to completion.

        Runs in real wall-clock time at session.sampling_rate_hz.
        Each observation is persisted privately and broadcast to
        all WebSocket subscribers of the contest.

        The session ends naturally when wall-clock time reaches
        contest.end_date. It cannot be paused or cancelled by
        participants.

        Raises PluginExecutionError if the twin or scenario cannot
        be loaded, or if a fatal error occurs during the loop.
        """
        pass

    def get_session_status(self, session_id: str) -> SessionStatus:
        pass
```

---

# Session Lifecycle

A session is created when the contest transitions to ACTIVE and transitions through:

```text
CREATED
    ↓  (engine starts the loop)
RUNNING
    ↓  (wall-clock reaches contest.end_date)
COMPLETED

    or

    ↓  (unrecoverable plugin exception)
FAILED
```

The engine is responsible for updating session status in storage at each transition. There is no CANCELLED state — only the platform can stop a session, and only by closing the contest.

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
8.  While wall-clock time < contest.end_date:
        a.  Advance virtual time: t += dt  (dt = 1 / sampling_rate_hz)
        b.  Activate/deactivate faults according to schedule
        c.  Call twin.step(state, dt) → new_state
        d.  Call fault.apply(new_state, dt) for each active non-SensorFault
            (faults modify new_state in place)
        e.  For each sensor in twin.get_sensors():
                raw = sensor.observe(new_state)
                For each active SensorFault targeting this sensor:
                    raw = sensor_fault.apply_to_measurement(raw)
        f.  Assemble SensorObservation (sensors dict only, for broadcast)
        g.  Build full observation with labels (for private storage)
        h.  Persist full observation to database (private — never exposed to participants)
        i.  Broadcast sensor readings only to all WebSocket subscribers of the contest
        j.  Sleep until next tick (wall-clock alignment)
        k.  state = new_state
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

The engine always produces ground-truth labels at each time step:

```python
labels = {
    "is_anomaly": len(active_faults) > 0,
    "fault_ids": [f.fault_id for f in active_faults],
    "severities": {f.fault_id: f.current_severity for f in active_faults},
}
```

Labels are persisted to the database as part of every `SensorObservation` record. They are never included in the WebSocket broadcast to participants. The scoring engine reads them directly from the database when evaluating submissions.

---

# WebSocket Broadcasting

The engine maintains a broadcast queue per contest session. All connected WebSocket clients for a contest share the same queue.

```text
SimulationEngine
      ↓  (produces observation)
ContestBroadcaster
      ↓  (fan-out to all subscribers)
WebSocketHandler × N
      ↓  (WebSocket.send_json per client)
Client × N
```

The message sent to participants contains sensor readings only:

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

Labels and fault metadata are never included.

Each client has its own bounded output queue. If a client is too slow to consume, its oldest messages are dropped. The engine's main loop is never blocked by slow clients. Observations are always persisted to the database regardless of client speed.

---

# Simulation Clock

The engine uses wall-clock time as the primary clock. The simulation runs in real time: one simulated second equals one real second.

Between steps the engine sleeps for `dt` seconds (`dt = 1 / sampling_rate_hz`) to align with real time. The `SensorObservation.timestamp` records the actual wall-clock time of each observation.

The competition's `end_date` is the natural termination condition. The engine checks wall-clock time against `contest.end_date` at each step.

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

# Design Requirement

The simulation engine must be fully testable without a real digital twin.

The Core must provide a `MockTwin` and `MockScenario` for use in unit tests of the engine itself.

See [Testing](testing.md) for details.
