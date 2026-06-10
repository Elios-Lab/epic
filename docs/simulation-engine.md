# Simulation Engine

> Related: [Digital Twins](digital-twins.md) · [Sensors](sensors.md) · [API Specification](api-specification.md)

The Simulation Engine is the EPIC Core component responsible for running digital twin simulations, collecting sensor observations, and delivering results to participants.

The engine is domain-independent. It interacts with the twin exclusively through the `DigitalTwin` interface and with sensors through the `Sensor` interface. It has no knowledge of fault logic, physical quantities, or domain-specific behaviour.

---

# Responsibilities

The engine owns the simulation loop across both contest phases. At session start it calls `twin.configure()` once; then, at every time step, it calls `twin.step()` to advance the physics and `sensor.observe()` for each configured sensor to produce the participant-visible measurements. Alongside each corrupted measurement it reads the clean latent-state value directly from the new state — before any sensor degradation — and collects ground-truth fault labels via `twin.get_active_faults()`. During the observation phase it broadcasts sensor readings to WebSocket subscribers without persisting them; during the evaluation phase it does the opposite, persisting full observations (sensors, ground truth, and labels) without broadcasting. At the boundary between the two phases it emits the `evaluation_started` event so clients can close cleanly, and throughout the session it manages the status transitions described below.

Equally explicit is what the engine does *not* do. It never activates or applies faults — the twin manages those internally. It does not manage contests, evaluate submissions, authenticate anyone, or route API requests. The engine is a loop around two interfaces, nothing more.

---

# Execution Model

Each contest has exactly one simulation session. It starts when the contest transitions to ACTIVE and runs in real wall-clock time until the contest transitions to CLOSED.

The engine runs the session continuously at `sampling_rate_hz`. Each observation serves two audiences through two different channels: during the evaluation phase it is persisted to the database with full labels, privately, for scoring only; during the observation phase it is broadcast to all connected WebSocket clients, carrying sensor readings only and never labels.

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

        i.  Sleep until the next absolute tick (wall-clock alignment,
            drift-free: computation time is absorbed by the remaining slot).

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

EPIC runs in **real-time lockstep**: each simulation step is anchored to an absolute tick `dt` seconds after the previous one, and the engine sleeps only for the remainder of the current slot after the step's computation is done. Computation time therefore never accumulates as drift; if a step overruns its slot entirely, the schedule re-anchors instead of letting the backlog grow. There is no time-acceleration and no batch mode. One second of simulated physics takes one second of wall-clock time.

This is an intentional design choice with several consequences. Participants receive observations at the actual sampling rate, just as they would from a physical sensor, and all time-based effects — fault growth, drift, integration — evolve at the correct physical rate. The contest has a real `end_date` checked against the wall clock. Most importantly, temporal honesty becomes enforceable: a participant cannot observe a future reading, because future readings do not exist yet.

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

Raising the sampling rate (shrinking `dt`) improves several things at once: numerical integration becomes more accurate and fault and drift effects are resolved more finely, participants get more data points per second to train on, and the unsafe window between the live edge of the stream and the last committed database batch shrinks. The price is database load — every step produces one `SensorObservation` row during the evaluation phase, committed in batches of ten — and CPU time spent in the twin's `step()`. The right value therefore follows the dynamics of the simulated system: around 1 Hz is enough for slow thermal or environmental systems like the smart building, 10–20 Hz suits mechanical systems whose oscillations need to be visible, and rates up to 100 Hz are reserved for vibration or electrical signals where the spectral content is the point.

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

If `session.seed` is set, the engine creates a dedicated `random.Random(seed)` instance for the session and injects it into every sensor whose constructor declares an `rng` parameter — all built-in sensors do, through `_BaseSensor`. Because each session owns its generator, concurrent sessions never interleave their random draws, so the same seed reproduces the same noise sequence regardless of what else the server is running.

As a backward-compatibility fallback the engine also seeds the global generators (`random.seed(seed)` and `np.random.seed(seed)`), so third-party sensors that use module-level random functions still benefit from seeding — but only reliably when a single session is running. Plugin authors should accept the injected `rng` instead.

---

# Error Handling

If `twin.step()` or `sensor.observe()` raises an exception, the engine sets session status to `FAILED`, stores the error message in `session.metadata["error"]`, and cancels the asyncio task.

Plugin exceptions are never propagated to the API layer. See [Error Handling](error-handling.md).

---

# Design Requirement

The engine must be fully testable without a real digital twin or sensor. `epic_core/testing.py` provides `MockTwin` and `MockSensor` for this purpose. See [Testing](testing.md).
