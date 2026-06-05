# Fault Framework

> Related: [Digital Twins](digital-twins.md) · [Sensors](sensors.md) · [Contest Authoring](contest-authoring.md)

Faults model physical degradations of a simulated system — mechanical wear, parameter drift, electrical failures, environmental disturbances. They are the primary source of machine learning challenges in EPIC: participants must detect, classify, forecast, or anticipate system degradation from sensor observations alone.

**Faults are entirely owned and managed by the digital twin.** The engine never touches fault objects. The contest configuration specifies which faults to inject and when; the twin receives this schedule and handles everything internally.

**Sensor degradations are not faults.** False readings, outliers, stuck values, and dropout are intrinsic sensor properties modelled as sensor parameters. See [Sensors](sensors.md).

---

# Design Philosophy

A fault modifies how the twin computes its dynamics. It always acts inside `twin.step()`, before sensors observe the state.

```text
twin.step(state, dt)
      ↓
  1. advance internal time
  2. activate / deactivate faults per schedule
  3. compute dynamics
  4. apply active fault effects
  5. return new state
      ↓
sensor.observe(new_state, dt)
```

The engine never calls `fault.activate()`, `fault.apply()`, or any other fault method. The twin manages the full lifecycle.

---

# FaultDescriptor Interface

The only fault interface visible to the Core is `FaultDescriptor`. It exists for two purposes: API listing and contest validation.

```python
class FaultDescriptor(ABC):

    @property
    @abstractmethod
    def fault_id(self) -> str:
        """Unique identifier within this twin, e.g. 'increased_damping'."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        """
        Return fault metadata. Must include at minimum:
            {
                "fault_id": str,
                "name": str,
                "description": str
            }
        """
        pass
```

`FaultDescriptor` instances are returned by `twin.get_faults()`. The engine uses them only to validate that a contest's `fault_schedule` references real fault IDs. The API uses them to let contest authors browse available faults.

---

# Implementing Faults Inside a Twin

Fault implementations are private to the twin package. There is no required base class beyond what the twin author chooses to use internally.

A simple approach: store fault state inside the twin itself.

```python
# Inside MechanicalTwin

class IncreasedDampingFault(FaultDescriptor):
    fault_id = "increased_damping"
    name = "Increased Damping"

    def metadata(self):
        return {
            "fault_id": self.fault_id,
            "name": self.name,
            "description": "Gradually increases the damping coefficient.",
        }


class MechanicalTwin(DigitalTwin):

    def __init__(self):
        self._faults = [IncreasedDampingFault(), ...]
        self._active_faults: dict[str, float] = {}
        self._fault_schedule: list[dict] = []
        self._t = 0.0

    def get_faults(self):
        return self._faults

    def configure(self, initial_conditions, fault_schedule):
        self._t = 0.0
        self._fault_schedule = fault_schedule or []
        self._active_faults = {}
        return self._build_state(initial_conditions)

    def step(self, state, dt):
        self._t += dt
        self._tick_fault_schedule()
        new_state = self._compute_dynamics(state, dt)
        self._apply_faults(new_state, dt)
        return new_state

    def _tick_fault_schedule(self):
        for entry in self._fault_schedule:
            fid = entry["fault_id"]
            active = (
                self._t >= entry["start_time"]
                and (entry["end_time"] is None or self._t < entry["end_time"])
            )
            if active:
                self._active_faults[fid] = entry["severity"]
            else:
                self._active_faults.pop(fid, None)

    def _apply_faults(self, state, dt):
        if "increased_damping" in self._active_faults:
            severity = self._active_faults["increased_damping"]
            state.damping *= (1.0 + severity)

    def get_active_faults(self):
        return [
            {"fault_id": fid, "severity": sev}
            for fid, sev in self._active_faults.items()
        ]
```

The implementation is completely free. The twin author decides how severities translate into physical effects, whether faults interact, and whether degradation is gradual or abrupt. The Core never constrains this.

---

# Fault Categories

Faults typically fall into one of two categories:

**Parameter faults** — alter system parameters, changing dynamics without directly modifying state variables.

Examples: increased damping, reduced stiffness, added friction.

```python
# Increased damping: higher damping coefficient → faster energy dissipation
state.damping = nominal_damping * (1.0 + severity)
```

**State faults** — directly modify state variables.

Examples: temperature spike, accelerated wear, sudden position offset.

```python
# Temperature rise fault
state.temperature += severity * 50.0 * dt
```

Both types are handled identically from the engine's perspective — the twin applies them inside `step()`.

---

# Fault Schedule Format

A contest's `fault_schedule` is a list of activation entries. Each entry specifies a fault by ID, a time window (in seconds from simulation start), and a severity level.

```json
[
  {
    "fault_id": "increased_damping",
    "start_time": 3600.0,
    "end_time": null,
    "severity": 0.3
  },
  {
    "fault_id": "reduced_stiffness",
    "start_time": 7200.0,
    "end_time": 10800.0,
    "severity": 0.5
  }
]
```

`start_time` and `end_time` are in seconds from simulation start (0 = contest start). `end_time: null` means the fault remains active until the session ends. `severity` is a float in [0.0, 1.0].

Multiple simultaneous faults are supported. The twin is responsible for applying them all correctly.

The platform validates at contest creation that every `fault_id` in the schedule is present in `twin.get_faults()`.

---

# Fault Validation at Contest Creation

The engine validates the fault schedule against the twin before a contest can become ACTIVE:

```python
available = {f.fault_id for f in twin.get_faults()}
for entry in contest.fault_schedule:
    if entry["fault_id"] not in available:
        raise EPICValidationError(
            f"fault '{entry['fault_id']}' is not available for twin '{twin.twin_id}'"
        )
```

If validation fails, the contest cannot be activated.

---

# Labels

After each `step()`, the engine calls `twin.get_active_faults()` to build ground-truth labels:

```json
{
  "is_anomaly": true,
  "fault_ids": ["increased_damping"],
  "severities": {"increased_damping": 0.3}
}
```

Labels are stored privately in every `SensorObservation` record and used by the scoring engine to evaluate anomaly detection and fault classification submissions. They are never sent to participants.

---

# Reproducibility

If a session has a seed, the engine seeds the global random state before starting the loop. Fault implementations that use probabilistic effects (intermittent faults, jitter in activation time) must use `random` or `numpy.random` module-level functions — not private RNG instances — so that seeding produces reproducible results.
