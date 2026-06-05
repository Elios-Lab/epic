# Digital Twin Development Guide

> Related: [Faults](faults.md) · [Sensors](sensors.md) · [Physical Quantities](quantities.md) · [Simulation Engine](simulation-engine.md)

A digital twin is a self-contained simulation of a physical system. It evolves an internal latent state over time, manages its own fault behaviour, and exposes observable quantities that sensors can read.

Examples of systems that can be modelled as twins:

- Mechanical systems (mass-spring-damper, rotating machinery)
- Industrial equipment (pumps, compressors, motors)
- Smart buildings
- Power grids
- Biomedical monitors
- Networked systems

---

# Design Philosophy

A twin models three things:

1. **Latent state** — the true internal variables of the system (position, velocity, temperature, bearing wear, …). Participants never observe these directly.
2. **Dynamics** — how the state evolves over time (`step()`).
3. **Fault management** — which faults are available, and how they alter dynamics when active.

Participants observe the system only through sensors configured at contest creation time. The twin's internal state remains hidden.

---

# Responsibilities

A digital twin must:

- define its latent state
- implement state evolution in `step()`
- declare which physical quantities its state provides (`supported_quantities()`)
- accept a fault schedule at session start (`configure()`) and manage fault activation entirely internally
- expose available fault descriptors for API listing and contest validation (`get_faults()`)
- report currently active faults for label generation (`get_active_faults()`)
- expose metadata

A digital twin must not:

- own sensors (sensors are independent and live in `epic_sensors/`)
- manage contests, users, submissions, or scores
- perform authentication

---

# DigitalTwin Interface

Every twin must implement the `DigitalTwin` abstract class from `epic_core/interfaces.py`.

```python
class DigitalTwin(ABC):

    @property
    @abstractmethod
    def twin_id(self) -> str:
        """Unique identifier, e.g. 'mechanical_system'."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def configure(
        self,
        initial_conditions: dict | None,
        fault_schedule: list[dict],
    ) -> SimulationState:
        """
        Called once by the engine before the simulation loop begins.

        Receives the contest's initial_conditions and fault_schedule.
        The twin stores the fault schedule internally and uses it during
        subsequent step() calls to activate faults at the correct times.

        Returns the initial SimulationState for the session.

        fault_schedule entries have the form:
            {
                "fault_id": "increased_damping",
                "start_time": 3600.0,   # seconds from simulation start
                "end_time": None,       # None = active until session ends
                "severity": 0.3         # [0.0, 1.0]
            }
        """
        pass

    @abstractmethod
    def step(self, state: SimulationState, dt: float) -> SimulationState:
        """
        Advance the simulation by one time step dt (in seconds).

        The twin is responsible for:
        1. Tracking internal simulation time.
        2. Activating or deactivating faults according to the stored schedule.
        3. Computing system dynamics.
        4. Applying the effects of currently active faults to the dynamics.
        5. Returning the new SimulationState.

        Must return a new SimulationState. Must not modify state in place.
        """
        pass

    @abstractmethod
    def get_active_faults(self) -> list[dict]:
        """
        Return the list of currently active faults.

        Called by the engine after each step() solely for label generation.
        Must be read-only — must not change any twin state.

        Return format:
            [{"fault_id": "increased_damping", "severity": 0.3}, ...]
        """
        pass

    @abstractmethod
    def supported_quantities(self) -> set[PhysicalQuantity]:
        """
        Return the set of physical quantities this twin's state can provide.

        Used to validate sensor compatibility at session start.
        """
        pass

    @abstractmethod
    def get_faults(self) -> list[FaultDescriptor]:
        """
        Return descriptors for all faults this twin supports.

        Used by the API to list available faults and by the engine to
        validate fault_ids in a contest's fault_schedule.
        """
        pass

    @abstractmethod
    def metadata(self) -> dict:
        """
        Return twin metadata. Must include at minimum:
            {
                "twin_id": str,
                "name": str,
                "version": str,   # semver, e.g. "1.0.0"
                "description": str
            }
        """
        pass
```

---

# Latent State

The latent state holds the true internal variables of the simulated system. It must implement `SimulationState` so sensors can read physical quantities.

```python
class SimulationState(ABC):

    @abstractmethod
    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        """
        Return the current value for a physical quantity.
        Return None if this state does not model the requested quantity.

        This is the only interface through which sensors access the twin's
        state. No sensor may access state fields directly.
        """
        pass
```

Concrete twins define their own state dataclass:

```python
@dataclass
class MechanicalState(SimulationState):
    position: float
    velocity: float
    acceleration: float
    temperature: float
    mass: float
    stiffness: float
    damping: float

    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        return {
            PhysicalQuantity.LINEAR_POSITION:     self.position,
            PhysicalQuantity.LINEAR_VELOCITY:     self.velocity,
            PhysicalQuantity.LINEAR_ACCELERATION: self.acceleration,
            PhysicalQuantity.TEMPERATURE:         self.temperature,
        }.get(quantity)
```

The Core never accesses state fields directly. Physical quantities are the only interface.

---

# Fault Management

Fault management is entirely internal to the twin. The engine never activates, deactivates, or applies fault objects. The twin receives the fault schedule once via `configure()` and is solely responsible for everything that follows.

A typical implementation pattern:

```python
def configure(self, initial_conditions, fault_schedule):
    self._t = 0.0
    self._fault_schedule = fault_schedule or []
    self._active_faults: dict[str, float] = {}   # fault_id -> severity
    return self._build_initial_state(initial_conditions)

def step(self, state, dt):
    self._t += dt
    self._update_active_faults()
    new_state = self._compute_dynamics(state, dt)
    self._apply_active_faults(new_state, dt)
    return new_state

def _update_active_faults(self):
    for entry in self._fault_schedule:
        fid = entry["fault_id"]
        started = self._t >= entry["start_time"]
        ended = entry["end_time"] is not None and self._t >= entry["end_time"]
        if started and not ended:
            self._active_faults[fid] = entry["severity"]
        else:
            self._active_faults.pop(fid, None)

def get_active_faults(self):
    return [
        {"fault_id": fid, "severity": sev}
        for fid, sev in self._active_faults.items()
    ]
```

See [Faults](faults.md) for guidance on implementing fault effects on dynamics.

---

# Physical Quantities and Sensors

The twin declares which physical quantities its state provides. Any sensor in `epic_sensors/` that measures one of those quantities is automatically compatible.

```python
def supported_quantities(self) -> set[PhysicalQuantity]:
    return {
        PhysicalQuantity.LINEAR_POSITION,
        PhysicalQuantity.LINEAR_VELOCITY,
        PhysicalQuantity.LINEAR_ACCELERATION,
        PhysicalQuantity.TEMPERATURE,
    }
```

Sensor compatibility is validated by the engine at session start. See [Physical Quantities](quantities.md) and [Sensors](sensors.md).

---

# Digital Twin Lifecycle in a Contest

```text
Contest created: twin_id, sensor_configs, fault_schedule, initial_conditions
      ↓
Contest transitions to ACTIVE
      ↓
Engine calls twin.configure(initial_conditions, fault_schedule)  → initial state
      ↓
Simulation loop:
      twin.step(state, dt)           ← dynamics + internal fault management
      sensor.observe(new_state, dt)  ← measurement per configured sensor
      twin.get_active_faults()       ← labels written to private storage
      broadcast sensor readings to participants
      ↓
Contest transitions to CLOSED → session COMPLETED
```

---

# Reference Twin: Mechanical System

The first EPIC twin is a mass-spring-damper:

```
m·x'' + c·x' + k·x = F(t)
```

State variables: `position`, `velocity`, `acceleration`, `temperature`.

System parameters: `mass`, `stiffness`, `damping`.

Available faults (see [Faults](faults.md)):

- `increased_damping` — gradually increases the damping coefficient
- `reduced_stiffness` — gradually reduces the stiffness coefficient
- `increased_friction` — adds energy dissipation, raising temperature

---

# Registration

A twin becomes available by registering it at application startup:

```python
from epic_core.registry import twin_registry
from epic_twins.mechanical.twin import MechanicalTwin

twin_registry.register(MechanicalTwin())
```

After registration, the platform exposes the twin through `GET /api/v1/twins` and related endpoints automatically. No Core file needs to be modified.

---

# Adding a New Twin

1. Define a `SimulationState` subclass with `get_quantity()`.
2. Implement `DigitalTwin`: `configure()`, `step()`, `get_active_faults()`, `supported_quantities()`, `get_faults()`, `metadata()`.
3. Register at startup.

No EPIC Core file needs to be modified.
