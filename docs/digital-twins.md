# Digital Twins

A digital twin is a self-contained simulation of a physical system. It evolves an internal latent state over time, manages its own fault behaviour, and exposes observable quantities that sensors can read. Almost any dynamical system can be modelled as a twin: mechanical systems such as a mass-spring-damper or rotating machinery, industrial equipment such as pumps, compressors and motors, but equally smart buildings, power grids, biomedical monitors, or networked systems.

This document covers both sides of the topic. Part I is the catalog of the five twins that ship with EPIC — what each one simulates, which quantities and faults it exposes, and how to choose one when authoring a contest. Part II is the development guide for implementing a new twin against the `DigitalTwin` interface.

A twin models three things. The first is its **latent state**, the true internal variables of the system — position, velocity, temperature, bearing wear — which participants never observe directly. The second is its **dynamics**, how that state evolves over time, implemented in `step()`. The third is **fault management**: which faults are available, and how they alter the dynamics when active. Participants observe the system only through sensors configured at contest creation time; the twin's internal state remains hidden.

---

## The Built-in Catalog

Each built-in twin is a self-contained Python package under `epic_twins/`, registered at application startup and exposed through `GET /api/v1/twins`.

A note on fidelity is in order before the individual descriptions. These twins are intentionally simple. They are first-order behavioral models, not high-fidelity engineering simulators: their purpose is to produce sensor streams that are physically plausible, react believably to faults, and remain fast enough to run in real time at tens of hertz. For a machine learning competition this is exactly what is needed — the difficulty of the challenge comes from noise, drift, fault dynamics, and the forecasting horizon, not from the complexity of the underlying differential equations.

All five twins share the same internal structure. Each one keeps a private fault schedule received from the contest configuration, advances an internal clock on every `step()` call, activates and deactivates faults when the clock crosses the scheduled start and end times, and applies the effects of every active fault directly to the new state before returning it. The simulation engine never sees any of this machinery; it only calls the `DigitalTwin` interface methods. Severity is a number between 0 and 1 that scales the strength of every fault effect, and because most fault effects accumulate over time (they are proportional to the time step `dt`), a fault left active for a long period produces a gradual, realistic degradation rather than a sudden jump.

### Mass-Spring-Damper (`mass_spring_damper`)

The mass-spring-damper is the simplest twin in the catalog and the best starting point for understanding the platform. It simulates a single mass attached to a spring and a viscous damper, driven by a sinusoidal external force of 0.5 N at 1 Hz. At every step the twin integrates the classical equation of motion — acceleration equals force minus damping times velocity minus stiffness times position, all divided by mass — using simple semi-implicit Euler integration. The result is a smooth oscillatory motion whose amplitude and phase shift respond to any change in the physical parameters, which is precisely what the faults exploit.

The twin exposes four physical quantities: linear position, linear velocity, linear acceleration, and temperature. The first three describe the motion of the mass, while temperature exists mainly as a side channel for the friction fault. Any sensor measuring one of these quantities can be attached, which in the built-in library means the position, velocity, acceleration, and temperature sensors.

The default configuration starts the mass at 0.1 m from rest, with a mass of 1 kg, a stiffness of 10 N/m, a damping coefficient of 0.5 N·s/m, and an ambient temperature of 20 °C. An organizer can override any of these through the contest's `initial_conditions` field, using the keys `position`, `velocity`, `temperature`, `mass`, `stiffness`, and `damping`.

Three faults are available. *Reduced stiffness* (`reduced_stiffness`) progressively weakens the spring, multiplying the stiffness by a factor slightly below one at every step; the stiffness never falls below 1 N/m, and the visible effect is an oscillation that slowly lengthens its period and changes amplitude. *Increased damping* (`increased_damping`) does the opposite kind of damage, growing the damping coefficient so that the oscillation dies down faster than it should. *Increased friction* (`increased_friction`) combines a mild damping increase with a steady temperature rise, so it is the only fault on this twin that becomes visible through the temperature sensor as well as through the motion.

The built-in contest template `spring_damper_stiffness_loss` uses this twin with position, velocity, and temperature sensors at 20 Hz, and schedules a stiffness-loss fault of severity 0.6 starting fifteen seconds into the simulation.

### Industrial Centrifugal Pump (`industrial_pump`)

The industrial pump twin models a centrifugal pump operating in steady state, with slow periodic load variation. Flow rate and discharge pressure oscillate gently around their nominal values (a 3% and 2% modulation at 0.2 Hz, slightly out of phase with each other), which gives participants a realistic baseline signal that is neither constant nor trivially periodic. On top of this baseline, the twin maintains a hidden *wear* variable between 0 and 1 that grows slowly throughout the simulation. Wear is never directly observable, but it drives both the temperature trend and the vibration baseline: as wear accumulates, the pump runs hotter and vibrates more. This hidden-state design makes the pump a natural candidate for predictive-maintenance-flavored challenges, because the observable signals carry indirect evidence of a degradation process the participant cannot measure directly.

The twin exposes flow rate, pressure, temperature, and vibration, matching the built-in flow rate (m³/h), pressure (bar), temperature (°C), and vibration (mm/s) sensors. Defaults place the pump at 120 m³/h, 4 bar, 35 °C, a vibration baseline of 1 mm/s, and an initial wear of 0.05; all of these can be overridden through `initial_conditions` using the keys `flow_rate`, `pressure`, `temperature`, `vibration`, and `wear`.

The three available faults reflect the classic failure modes of a real centrifugal pump. *Cavitation* (`cavitation`) simulates vapor bubbles forming at the impeller: the flow rate drops by up to 12% at full severity and vibration jumps immediately, making it the most abrupt and detectable of the three. *Bearing wear* (`bearing_wear`) accelerates the hidden wear variable and adds both vibration and a slow temperature climb, producing a gradual degradation signature spread across multiple sensors. *Filter clog* (`filter_clog`) restricts the flow while raising discharge pressure, a distinctive combination — flow down, pressure up — that differentiates it cleanly from cavitation for fault-diagnosis purposes.

The `pump_bearing_fault` template runs this twin at 10 Hz with all four sensors active and a bearing-wear fault of severity 0.7 starting at twenty seconds.

### Three-Phase Induction Motor (`electric_motor`)

The electric motor twin represents a three-phase induction motor running at a nominal operating point, with two superimposed periodic effects: a 50 Hz supply-frequency ripple on current and voltage, and a slow 0.5 Hz load oscillation on speed and torque. Temperature rises continuously at a rate proportional to the load factor, so even a healthy motor warms up slowly over the course of a contest — participants who model temperature as a constant will be systematically wrong, which is intentional.

The twin exposes five quantities — current, voltage, rotational speed, temperature, and torque — of which the first four have matching built-in sensors (current in A, voltage in V, rotational speed in RPM, temperature in °C). Torque is exposed as a quantity but has no built-in sensor yet, so it remains a latent variable in practice. Defaults are 12 A, 400 V, 1450 RPM, 40 °C, and 80 N·m, overridable through the keys `current`, `voltage`, `speed`, `temperature`, and `torque`.

The fault set covers electrical, mechanical, and thermal failure modes. *Voltage imbalance* (`voltage_imbalance`) is the electrical fault: current rises by up to 12%, torque drops by up to 10%, and the motor heats faster, all proportional to severity. *Bearing fault* (`bearing_fault`) is the mechanical one, adding a progressive speed deviation and extra heat. *Overheating* (`overheating`) is the most interesting from a modeling standpoint because it has a threshold behavior: it accelerates the temperature rise unconditionally, but only once the motor crosses 80 °C does it start degrading speed and torque, with the degradation growing as the temperature climbs further. A contest long enough for the motor to cross that threshold therefore exhibits a regime change in the sensor streams.

The `motor_voltage_imbalance` template samples this twin at 50 Hz — the highest rate among the templates, chosen to make the supply-frequency ripple visible — with a voltage-imbalance fault of severity 0.5 from ten seconds onward.

### Rotating Shaft and Gearbox (`rotating_machinery`)

The rotating machinery twin models a driven shaft with a gearbox, the canonical subject of industrial vibration monitoring. Its baseline behavior combines three periodic components at different frequencies: a slow 0.15 Hz load oscillation that modulates power consumption by ±8%, a small 0.5 Hz speed wobble, and a faster 1.5 Hz vibration component. Temperature rises with the load factor, and the twin also tracks a shaft-deflection variable that oscillates gently in healthy operation. Shaft deflection, like pump wear, is internal: it is not exposed as a physical quantity, but the faults push on it and its effects feed the observable vibration signal.

Exposed quantities are rotational speed, vibration, temperature, and power, matching the built-in rotational speed (RPM), vibration (mm/s), temperature (°C), and power (W) sensors. The defaults describe a substantial industrial machine: 1800 RPM, 75 kW, a vibration baseline of 1.2 mm/s, and 45 °C, overridable through `speed`, `vibration`, `temperature`, `power`, and `shaft_deflection`.

The faults are the three classics of rotating-equipment diagnostics. *Unbalance* (`unbalance`) adds vibration proportionally to the current shaft speed — its signature scales with RPM, exactly as a real mass imbalance does. *Misalignment* (`misalignment`) raises vibration by a speed-independent amount and additionally increases power draw by up to 8% and heats the machine, reflecting the extra work done against the misaligned coupling. *Gear tooth wear* (`gear_tooth_wear`) produces a slower, accumulating signature: moderate immediate vibration plus steadily growing heat and shaft deflection, suited to long-horizon degradation scenarios.

The `gearbox_tooth_wear` template runs at 25 Hz with all four sensors and a gear-tooth-wear fault of severity 0.8 starting at twenty-five seconds.

### Smart Commercial Building Floor (`smart_building`)

The smart building twin is deliberately different from the other four: it simulates an environment rather than a machine, and its dynamics are driven by occupancy and thermal exchange rather than by rotating parts. The model represents one floor of a commercial building with an HVAC system holding a target temperature of 22 °C against an outdoor temperature of 30 °C. Occupancy fluctuates around its nominal value with a short sinusoidal cycle, and every occupant adds CO₂ and humidity to the indoor air while ventilation pulls CO₂ back down toward an outdoor baseline of roughly 420 ppm. Indoor temperature is the balance of two opposing terms — heat leaking in through the building envelope and the HVAC correction pulling toward the setpoint — while HVAC power itself is observable as it ramps up and down with the magnitude of the temperature error. CO₂ is floored at 400 ppm and humidity is clamped between 20% and 80%, so the signals stay within physically sensible ranges.

The twin exposes temperature, humidity, CO₂ concentration, and occupancy, all four with matching built-in sensors (temperature in °C, relative humidity in %RH, CO₂ in ppm, occupancy in people). Defaults are 22 °C, 45% relative humidity, 650 ppm of CO₂, 20 occupants, and 3.5 kW of HVAC capacity, with overridable keys `temperature`, `humidity`, `co2`, `occupancy`, `hvac_power`, `target_temperature`, and `outdoor_temperature`. The last two are particularly useful for authoring scenarios: raising the outdoor temperature or lowering the HVAC capacity changes the whole thermal balance of the simulation without touching any code.

The faults model building-operations incidents rather than mechanical damage. *HVAC failure* (`hvac_failure`) scales the conditioning power down — at full severity the HVAC stops entirely — and lets CO₂ accumulate, so the indoor climate drifts toward outdoor conditions while air quality degrades. *Occupancy spike* (`occupancy_spike`) injects a sustained crowd of additional people with the corresponding CO₂ and humidity load, simulating an event or an over-booked floor. *Sensor drift* (`sensor_drift`) progressively biases the temperature and humidity values; conceptually this represents miscalibrated building instrumentation, and it is worth noting that it is implemented as a twin fault acting on the latent state, which means it also shifts the recorded ground truth — unlike the per-sensor drift parameter described in [Sensors](sensors.md), which corrupts only the measurement.

The `building_hvac_failure` template runs at 2 Hz — environmental dynamics are slow, and a low sampling rate keeps the data volume proportionate — with an HVAC failure of severity 0.9 from thirty seconds onward.

### Choosing a Twin for a Contest

For a first contest or a teaching scenario, the mass-spring-damper is the natural choice: its dynamics are visible to the naked eye in a plotted sensor stream, the connection between fault and effect is easy to explain, and a simple physical model can compete respectably, which keeps the focus on methodology. The industrial pump and the rotating machinery twins suit predictive-maintenance narratives, because both carry hidden degradation states whose indirect signatures reward feature engineering across multiple sensors. The electric motor offers the richest spectral content thanks to its 50 Hz supply ripple and is the best fit when the pedagogical goal involves higher sampling rates or frequency-domain analysis. The smart building, finally, is the slowest and most accessible of the five for audiences without an engineering background, and its configurable setpoint and outdoor conditions make it the most flexible for scenario design through configuration alone.

Whatever the choice, the contest author workflow is identical for every twin, because the platform interacts with all of them through the same interface. The available sensors are constrained only by the quantities the twin exposes, the fault schedule accepts any of the fault identifiers listed above for the chosen twin, and every parameter mentioned in this catalog is set through the same `initial_conditions`, `sensor_configs`, and `fault_schedule` fields described in [Contests](contest.md).

---

## Implementing a New Twin

### Responsibilities

A digital twin owns everything about the simulated system and nothing about the platform around it. It defines its latent state and implements state evolution in `step()`. It declares which physical quantities that state provides through `supported_quantities()`, which is how the engine validates sensor compatibility. It accepts a fault schedule once, at session start, through `configure()`, and from then on manages fault activation entirely internally; it exposes the available fault descriptors through `get_faults()` so the API can list them and contest configurations can be validated, and reports currently active faults through `get_active_faults()` so the engine can generate ground-truth labels. Finally, it exposes descriptive metadata.

Just as important is what a twin must *not* do. It does not own sensors — sensors are independent components living in `epic_sensors/`, coupled to the twin only through physical quantities. It knows nothing about contests, users, submissions, or scores, and it plays no part in authentication. A twin that needs any of these things is a design error.

### DigitalTwin Interface

Every twin must implement the `DigitalTwin` abstract class from `epic_core/interfaces.py`.

```python
class DigitalTwin(ABC):

    @property
    @abstractmethod
    def twin_id(self) -> str:
        """Unique identifier, e.g. 'mass_spring_damper'."""
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

### Latent State

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
class MassSpringDamperState(SimulationState):
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

### Fault Management

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

### The FaultDescriptor Interface

Faults model physical degradations of the simulated system — mechanical wear, parameter drift, electrical failures, environmental disturbances — and are the primary source of machine learning challenges: participants must detect, classify, forecast, or anticipate degradation from sensor observations alone. Sensor degradations are *not* faults: false readings, outliers, and dropout are intrinsic sensor properties modelled as sensor parameters (see [Sensors](sensors.md)).

The only fault abstraction visible to the Core is `FaultDescriptor`, and it exists for exactly two purposes: API listing and contest validation.

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
        """Must include at minimum fault_id, name, description."""
        pass
```

Descriptor instances are returned by `twin.get_faults()`. The engine uses them only to validate that a contest's `fault_schedule` references real fault ids before a session starts; the API uses them so contest authors can browse what is available. Everything else about a fault — how a severity translates into physical effects, whether faults interact, whether degradation is gradual or abrupt — is private to the twin package, and the Core never constrains it. The built-in twins pair each descriptor with an `apply(state, severity, dt)` method that the twin calls from its own `step()`, but that is a convention, not a requirement.

### Writing Fault Effects

Fault effects typically fall into two categories, handled identically from the engine's perspective because both happen inside `step()`. *Parameter faults* alter system parameters, changing the dynamics without touching state variables directly — increased damping, reduced stiffness, added friction:

```python
state.damping = nominal_damping * (1.0 + severity)
```

*State faults* modify state variables directly — a temperature rise, accelerated wear, a sudden offset:

```python
state.temperature += severity * 50.0 * dt
```

Severity is a float in `[0, 1]`; effects proportional to `dt` accumulate over time and produce gradual, realistic degradation, which is usually what a contest wants. Multiple simultaneous faults are supported, and the twin is responsible for applying them all correctly. The schedule format an organizer writes (`fault_id`, `start_time`, `end_time`, `severity`) is documented in the authoring guide of [Contests](contest.md); the platform validates every scheduled `fault_id` against `get_faults()` at contest creation, so an invalid schedule can never reach a running session.

After each `step()` the engine calls `get_active_faults()` and stores the result as ground-truth labels (`is_anomaly`, `fault_ids`, `severities`) in every evaluation-phase observation. Labels are private — used by scoring for anomaly detection and fault classification tasks, never sent to participants.

One reproducibility note: a fault with probabilistic behavior (intermittent activation, jittered onset) should draw from module-level `random` / `numpy.random` functions, which the engine seeds per session as a fallback; deterministic fault effects need nothing special.

### Physical Quantities and Sensors

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

Sensor compatibility is validated by the engine at session start. The ontology and the validation rules are documented in [Sensors](sensors.md).

### Lifecycle in a Contest

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

### Reference Implementation

The recommended reference to read first is the mass-spring-damper in `epic_twins/mass_spring_damper/` — the simplest twin in the catalog (its physics, faults, and defaults are described in Part I). Its three modules show the canonical layout: `twin.py` with the state dataclass and the `DigitalTwin` implementation, `faults.py` with the fault descriptors and their `apply()` effects, and `plugin.py` with the registration entry point.

### Registration

A twin becomes available by registering an instance at application startup:

```python
import epic_core.registry as registry_module
from epic_twins.mass_spring_damper.twin import MassSpringDamperTwin

registry_module.twin_registry.register(MassSpringDamperTwin())
```

The built-in twins wrap this call in a `plugin.py` module exposing a `register()` function, which the API application invokes in its startup hook. After registration, the platform exposes the twin through `GET /api/v1/twins` and related endpoints automatically. No Core file needs to be modified.

### Adding a New Twin, Step by Step

The whole process takes three steps. First, define a `SimulationState` subclass — typically a dataclass — that holds your latent variables and implements `get_quantity()`. Second, implement the `DigitalTwin` interface: `configure()`, `step()`, `get_active_faults()`, `supported_quantities()`, `get_faults()`, and `metadata()`. Third, register an instance at startup. The new twin appears in the API and can be used in contest configurations immediately; no EPIC Core file needs to be modified, and that property is the test of a correct implementation.
