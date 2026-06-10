# Digital Twin Development Guide

> Related: [Faults](faults.md) · [Sensors](sensors.md) · [Physical Quantities](quantities.md) · [Simulation Engine](simulation-engine.md)

A digital twin is a self-contained simulation of a physical system. It evolves an internal latent state over time, manages its own fault behaviour, and exposes observable quantities that sensors can read.

Almost any dynamical system can be modelled as a twin: mechanical systems such as a mass-spring-damper or rotating machinery, industrial equipment such as pumps, compressors and motors, but equally smart buildings, power grids, biomedical monitors, or networked systems. The five twins that ship with EPIC are described in the [Digital Twin Catalog](twin-catalog.md); this document explains how to build a new one.

---

# Design Philosophy

A twin models three things. The first is its **latent state**, the true internal variables of the system — position, velocity, temperature, bearing wear — which participants never observe directly. The second is its **dynamics**, how that state evolves over time, implemented in `step()`. The third is **fault management**: which faults are available, and how they alter the dynamics when active.

Participants observe the system only through sensors configured at contest creation time. The twin's internal state remains hidden.

---

# Responsibilities

A digital twin owns everything about the simulated system and nothing about the platform around it. It defines its latent state and implements state evolution in `step()`. It declares which physical quantities that state provides through `supported_quantities()`, which is how the engine validates sensor compatibility. It accepts a fault schedule once, at session start, through `configure()`, and from then on manages fault activation entirely internally; it exposes the available fault descriptors through `get_faults()` so the API can list them and contest configurations can be validated, and reports currently active faults through `get_active_faults()` so the engine can generate ground-truth labels. Finally, it exposes descriptive metadata.

Just as important is what a twin must *not* do. It does not own sensors — sensors are independent components living in `epic_sensors/`, coupled to the twin only through physical quantities. It knows nothing about contests, users, submissions, or scores, and it plays no part in authentication. A twin that needs any of these things is a design error.

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

# Reference Twin: Mass-Spring-Damper

The simplest EPIC twin, and the recommended reference implementation to read first, is the mass-spring-damper in `epic_twins/mass_spring_damper/`:

```
m·x'' + c·x' + k·x = F(t)
```

Its state carries the variables `position`, `velocity`, `acceleration`, and `temperature` together with the system parameters `mass`, `stiffness`, and `damping`. It supports three faults, all described in detail in the [Digital Twin Catalog](twin-catalog.md): `increased_damping`, which gradually increases the damping coefficient; `reduced_stiffness`, which gradually weakens the spring; and `increased_friction`, which adds energy dissipation and raises the temperature. See [Faults](faults.md) for guidance on writing fault effects like these.

---

# Registration

A twin becomes available by registering an instance at application startup:

```python
import epic_core.registry as registry_module
from epic_twins.mass_spring_damper.twin import MassSpringDamperTwin

registry_module.twin_registry.register(MassSpringDamperTwin())
```

The built-in twins wrap this call in a `plugin.py` module exposing a `register()` function, which the API application invokes in its startup hook. After registration, the platform exposes the twin through `GET /api/v1/twins` and related endpoints automatically. No Core file needs to be modified.

---

# Adding a New Twin

The whole process takes three steps. First, define a `SimulationState` subclass — typically a dataclass — that holds your latent variables and implements `get_quantity()`. Second, implement the `DigitalTwin` interface: `configure()`, `step()`, `get_active_faults()`, `supported_quantities()`, `get_faults()`, and `metadata()`. Third, register an instance at startup. The new twin appears in the API and can be used in contest configurations immediately; no EPIC Core file needs to be modified, and that property is the test of a correct implementation.
