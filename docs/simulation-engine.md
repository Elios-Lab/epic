# Simulation Engine

> Related: [Digital Twins](digital-twins.md) · [Sensors](sensors.md) · [API Specification](api-specification.md)

The Simulation Engine is the EPIC Core component responsible for running digital twin simulations, collecting sensor observations, and delivering results to participants.

The engine is domain-independent. It interacts with the twin exclusively through the `DigitalTwin` interface and with sensors through the `Sensor` interface. It has no knowledge of fault logic, physical quantities, or domain-specific behaviour.

---

# Responsibilities

The engine is responsible for:

- managing the simulation loop (observation phase + evaluation phase)
- calling `twin.configure()` once at session start
- calling `twin.step()` at each time step
- calling `sensor.observe()` for each configured sensor
- reading the clean latent-state value from `new_state` before any sensor corruption
- collecting ground-truth labels via `twin.get_active_faults()`
- persisting observations (sensors + ground_truth + labels) during the evaluation phase only
- broadcasting sensor readings to WebSocket subscribers during the observation phase
- emitting the `evaluation_started` event when the observation phase ends and closing the stream
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

There is no batch mode and no accelerated simulation. Organizers and administrators can pause and resume a running session; participants cannot.

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
    ↓  (wall-clock reaches end_of_observation + prediction_horizon_seconds)
COMPLETED

    or

    ↓  (contest status set to PAUSED by organizer or admin)
PAUSED
    ↓  (contest resumed — engine restarts on the same session)
RUNNING  →  COMPLETED

    or

    ↓  (unrecoverable exception in twin.step() or sensor.observe())
FAILED

    or

    ↓  (server restarted while session was RUNNING — recovery at startup)
PAUSED   ← organizer can resume manually
```

The engine updates session status in storage at each transition. On unclean server shutdown, the startup recovery routine detects sessions still in `RUNNING` or `CREATED` state and sets both the session and its contest to `PAUSED`. PENDING submissions from before the restart are automatically re-queued for scoring.

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

5.  sequence_id = last committed sequence_id for this session
    (0 on first start; resumes from the last committed observation after a pause)

    simulation_end = end_of_observation + prediction_horizon_seconds
    ← engine stops after the full evaluation window has been collected

6.  While wall-clock time < simulation_end:

        a.  sequence_id += 1

        b.  new_state = twin.step(state, dt)
            ← twin handles fault activation and application internally

        c.  For each sensor in contest_sensors:
                measurement = sensor.observe(new_state, dt)
                ← sensor applies its own degradation pipeline (noise, drift, …)
                raw = new_state.get_quantity(sensor.measured_quantity)
                ← clean latent-state value before any pipeline corruption

        d.  active_faults = twin.get_active_faults()
            labels = {
                "is_anomaly": len(active_faults) > 0,
                "fault_ids":  [f["fault_id"]  for f in active_faults],
                "severities": {f["fault_id"]: f["severity"] for f in active_faults},
            }

        e.  [Two-phase] If wall-clock time >= end_of_observation and not yet signalled:
                Broadcast {"event": "evaluation_started", …} to WebSocket.
                Stop broadcasting subsequent observations (stream effectively closes).
                Switch to evaluation phase: begin persisting observations.

        f.  Buffer SensorObservation (sensors + ground_truth + labels) for DB write.
                sensors      ← noisy measurements (participant-visible during obs phase)
                ground_truth ← clean latent values (server-side only; used for scoring)
                labels       ← fault metadata (server-side only)
            Only persisted during the evaluation phase (not during the observation phase).

        g.  Every commit_interval steps:
                Commit buffered observations to database.
                committed_through = sequence_id
                If contest.status == "PAUSED" or "CLOSED": break  ← graceful stop

        h.  [Observation phase only] Broadcast {
                timestamp, session_id, sequence_id,
                committed_through,
                sensors
            } to WebSocket subscribers.

        i.  Sleep dt seconds (wall-clock alignment).

        j.  state = new_state

7.  Commit any remaining buffered observations.

8.  Set session status to COMPLETED (or PAUSED if stopped by step 6g).
```

Step 6b is the only place the engine interacts with the twin during the loop. The engine has no fault schedule, no fault objects, and no activation logic of its own.

---

# Session Configuration

The engine reads its configuration from the `Contest` and `SimulationSession` records:

```python
contest.twin_id                    # which twin to load
contest.sensor_configs             # sensors + parameter overrides
contest.fault_schedule             # passed as-is to twin.configure()
contest.initial_conditions         # passed as-is to twin.configure()
contest.end_of_observation         # observation phase ends; stream closes
contest.prediction_horizon_seconds # evaluation window length; engine stops after this
session.sampling_rate_hz           # dt = 1 / sampling_rate_hz
session.seed                       # optional RNG seed
```

---

# The Meaning of dt

`dt` is derived directly from the sampling rate:

```python
dt = 1.0 / session.sampling_rate_hz
```

At 10 Hz → `dt = 0.1 s`. At 20 Hz → `dt = 0.05 s`.

## Simulation time equals wall-clock time

EPIC runs in **real-time lockstep**: after each simulation step the engine sleeps exactly `dt` real seconds before taking the next step. There is no time-acceleration and no batch mode. One second of simulated physics takes one second of wall-clock time.

This is an intentional design choice. It means:

- Participants receive observations at the actual sampling rate, just as they would from a physical sensor.
- All time-based effects (fault growth, drift, integration) evolve at the correct physical rate.
- The contest has a real `end_date` checked against the wall clock.
- Temporal honesty is enforceable: a participant cannot observe a future reading because future readings do not exist yet.

## How dt is used by each layer

**Twin physics** — `dt` is the numerical integration step in seconds. Euler integration advances the state by `dt` seconds of physics per call:

```python
new_velocity = state.velocity + state.acceleration * dt
new_position = state.position + new_velocity * dt   # semi-implicit Euler
```

Fault effects are also integrated over `dt`:

```python
state.temperature += heat_rate * severity * dt   # °C per second × dt
```

**Sensor pipeline** — `dt` drives time-dependent pipeline stages:

```python
self._drift += self.drift_rate * dt   # drift accumulates in units/second × dt
```

**Consequence: dt must match the integration accuracy requirements of the twin.** A very slow sampling rate (large `dt`) can cause the Euler integrator to diverge for stiff or oscillatory systems. As a rule of thumb, `dt` should be much smaller than the system's shortest natural period.

## Choosing sampling_rate_hz

| Concern | Effect of increasing sampling_rate_hz (smaller dt) |
|---|---|
| **Physics accuracy** | More accurate numerical integration; finer fault and drift resolution |
| **Observation density** | More data points per second for participants to collect |
| **DB write rate** | More `SensorObservation` rows per second (one commit every 10 steps) |
| **Submission anchor safety** | Smaller unsafe window between live edge and last committed batch |

Typical values: 1 Hz for slow thermal or environmental systems; 10–20 Hz for mechanical systems; up to 100 Hz for vibration or electrical signals.

## committed_through: the safe anchor boundary

Because observations are committed to the database in batches of 10 steps, a participant who anchors their forecast submission to the very latest sequence number they received may reference an observation that is not yet in the database. The engine therefore includes a `committed_through` field in every WebSocket message:

```text
committed_through = highest sequence_id guaranteed to be in the database
```

Participants and the SDK should anchor submissions to `committed_through - H` (where H is the forecast horizon) rather than the raw `sequence_id`, to guarantee that the anchor and all its horizon observations are queryable at submission time.

---

# WebSocket Broadcasting

## Observation-phase messages

During the observation phase the engine broadcasts one message per simulation step. Labels and ground-truth values are never included.

```json
{
  "timestamp": "2027-01-15T10:00:00.500Z",
  "session_id": "abc123",
  "sequence_id": 116,
  "committed_through": 110,
  "sensors": {
    "position": 0.15,
    "velocity": 1.82,
    "temperature": 31.5
  }
}
```

`sequence_id` is the current live observation. `committed_through` is the highest sequence number flushed to the database.

## Evaluation-phase transition event

When `end_of_observation` is reached the engine broadcasts a single phase-change event and then stops sending observation messages. Clients that receive this event know the stream is closing and that the submission window will open once `prediction_horizon_seconds` have elapsed.

```json
{
  "event": "evaluation_started",
  "observation_end_sequence_id": 400,
  "evaluation_steps": 20
}
```

After this event the WebSocket server closes the connection from the server side.

## Queue and back-pressure

Each client has its own bounded output queue. If a client is too slow to consume messages, its oldest messages are dropped silently. The engine's main loop is never blocked by slow clients.

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
