# EPIC Plugin System

The EPIC plugin system is the foundation of the platform.

The primary design goal is to allow new domains, digital twins, sensors, faults and scoring strategies to be integrated without modifying the EPIC Core.

All extensions must interact with the platform through well-defined interfaces.

The Core must depend only on abstractions.

---

# Design Principles

The plugin system follows five principles:

## Separation of Concerns

Each plugin is responsible only for its own domain logic.

## Dependency Inversion

The Core depends on interfaces.

Plugins depend on the Core interfaces.

## Extensibility

New plugins should be installable without modifying existing code.

## Discoverability

Plugins should be automatically discoverable through registries.

## Reusability

Sensors, faults and metrics should be reusable across different twins.

---

# Plugin Categories

EPIC supports the following plugin categories:

- Digital Twin Plugins
- Sensor Plugins
- Fault Plugins
- Scenario Plugins
- Scoring Plugins

---

# Digital Twin Interface

Every digital twin must implement the `DigitalTwin` interface.

```python
from abc import ABC, abstractmethod

class DigitalTwin(ABC):

    @property
    @abstractmethod
    def twin_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def create_initial_state(
        self,
        initial_conditions: dict | None = None
    ) -> SimulationState:
        """
        Create and return the initial latent state for a simulation session.

        The simulation engine calls this once at session start, passing the
        'initial_conditions' dict returned by Scenario.initialize() (if any).
        The twin merges those overrides with its own defaults.

        If initial_conditions is None or empty, return the twin's default
        initial state.
        """
        pass

    @abstractmethod
    def step(self, state: SimulationState, dt: float) -> SimulationState:
        """
        Advance the simulation by one time step dt (in seconds).

        Must return a new SimulationState. Must not modify state in place.
        The engine replaces the current state with the returned value.

        Typical implementation:
        1. Compute system dynamics
        2. Apply operating profile for this time step
        3. Return updated state
        (Faults are applied by the engine after this call.)
        """
        pass

    @abstractmethod
    def get_sensors(self) -> list[Sensor]:
        pass

    @abstractmethod
    def get_faults(self) -> list[Fault]:
        pass

    @abstractmethod
    def get_scenarios(self) -> list[Scenario]:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        """
        Return plugin metadata. Must include at minimum:
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

# Responsibilities of a Digital Twin

A digital twin is responsible for:

- defining latent state variables;
- evolving the system state;
- defining supported sensors;
- defining supported faults;
- defining supported scenarios;
- exposing metadata.

The twin is not responsible for:

- authentication;
- contest management;
- scoring;
- API routing.

---

# Simulation State Interface

The latent state is represented by a SimulationState.

```python
from abc import ABC

class SimulationState(ABC):
    pass
```

Concrete twins may extend it.

Example:

```python
@dataclass
class MechanicalState(SimulationState):
    position: float
    velocity: float
    acceleration: float
    temperature: float
```

The EPIC Core should treat states as opaque objects.

---

# Sensor Interface

Sensors transform latent variables into observations.

```python
from abc import ABC, abstractmethod

class Sensor(ABC):

    @property
    @abstractmethod
    def sensor_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def unit(self) -> str:
        pass

    @abstractmethod
    def observe(self, state) -> float:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass
```

---

# Sensor Pipeline

A sensor should be implemented as a measurement pipeline:

```text
latent variable
      ↓
gain
      ↓
bias
      ↓
noise
      ↓
saturation
      ↓
quantization
      ↓
measurement
```

Future versions may introduce:

- drift
- latency
- filtering
- frequency response
- calibration errors

---

# Fault Interface

Faults alter system behaviour.

```python
from abc import ABC, abstractmethod

class Fault(ABC):

    @property
    @abstractmethod
    def fault_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def current_severity(self) -> float:
        """
        Current severity in [0.0, 1.0].
        0.0 = no effect. 1.0 = maximum effect.
        The fault is responsible for evolving this value over time
        inside apply() (e.g. gradual faults increase it each step).
        """
        pass

    @abstractmethod
    def activate(self, initial_severity: float = 1.0) -> None:
        """
        Called by the engine when the fault schedule activates this fault.
        Set internal state to active and initialise severity.
        """
        pass

    @abstractmethod
    def deactivate(self) -> None:
        """
        Called by the engine when the fault schedule ends this fault.
        Reset internal state to inactive and severity to 0.0.
        """
        pass

    @abstractmethod
    def apply(self, state: SimulationState, dt: float) -> None:
        """
        Modify state in place to reflect fault effects for this time step.
        Also responsible for evolving current_severity if the fault is gradual.
        Called by the engine every step while the fault is active.
        """
        pass

    @abstractmethod
    def metadata(self) -> dict:
        """
        Return plugin metadata. Must include at minimum:
        {
            "fault_id": str,
            "name": str,
            "version": str,
            "description": str
        }
        """
        pass
```

`apply(state, dt)` is called by the simulation engine on every time step while the fault is active. For state and parameter faults, implementations modify `state` in place and evolve `current_severity`. For sensor faults, `apply()` is a no-op on the latent state — sensor-level corruption is handled separately (see below).

---

# Sensor Fault Interface

A `SensorFault` is a specialised `Fault` that corrupts a measurement after it is produced by a sensor, rather than modifying the latent state.

```python
class SensorFault(Fault):

    @property
    @abstractmethod
    def target_sensor_ids(self) -> list[str]:
        """
        Sensor ids this fault applies to.
        Return an empty list to apply to all sensors of the twin.
        """
        pass

    def apply(self, state: SimulationState, dt: float) -> None:
        # no-op: sensor faults do not modify the latent state
        pass

    @abstractmethod
    def apply_to_measurement(self, measurement: float) -> float:
        """
        Corrupt and return the sensor measurement.
        Called by the engine after sensor.observe(state).
        May use self.current_severity to scale the effect.
        """
        pass
```

The simulation engine applies `SensorFault.apply_to_measurement()` after calling `sensor.observe(state)`, so the corruption happens on the observable value only.

This separation keeps the `Fault` interface uniform while allowing the engine to distinguish fault categories without coupling to domain logic:

```text
Latent State
      ↓
step() + StateFault.apply() + ParameterFault.apply()
      ↓
sensor.observe(state)
      ↓
SensorFault.apply_to_measurement(measurement)
      ↓
SensorObservation
```

---

# Fault Categories

Faults may act on:

## State Variables

Examples:

- wear
- overheating
- friction increase

## System Parameters

Examples:

- reduced stiffness
- reduced efficiency

## Sensor Measurements

These are implemented as `SensorFault` subclasses (see above).

Examples:

- bias
- drift
- stuck values
- excessive noise

The Core distinguishes `SensorFault` from other faults only to determine the application point in the simulation pipeline (`apply()` vs `apply_to_measurement()`). It never inspects the fault's domain content.

---

# Scenario Interface

Scenarios define simulation conditions.

```python
from abc import ABC, abstractmethod

class Scenario(ABC):

    @property
    @abstractmethod
    def scenario_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def initialize(self) -> dict:
        """
        Return a dictionary of initial configuration for this scenario.

        The dictionary may contain:
        - 'initial_conditions': dict of state variable overrides passed to
          the twin's create_initial_state()
        - 'operating_profile': an OperatingProfile instance
        - 'parameters': dict of system parameter overrides (e.g. mass, stiffness)

        The simulation engine merges these values into the twin's defaults.
        The twin remains the source of truth for any key not present here.
        """
        pass

    @abstractmethod
    def get_fault_schedule(self) -> list[dict]:
        """
        Return a list of fault activation entries.

        Each entry is a dict with:
        - 'fault_id': str — registered fault to activate
        - 'start_time': float — simulation time (seconds) to activate
        - 'end_time': float | None — simulation time to deactivate, or None for indefinite
        - 'severity': float (0.0–1.0) — initial severity at activation

        Example:
        [
            {'fault_id': 'sensor_bias', 'start_time': 120.0, 'end_time': None, 'severity': 0.5}
        ]
        """
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass
```

---

# Operating Profiles

Operating profiles define system inputs over time.

Examples:

- constant load
- sinusoidal load
- random load
- piecewise operating modes

Interface:

```python
class OperatingProfile(ABC):

    @abstractmethod
    def value(self, t: float) -> float:
        pass
```

---

# Scoring Metric Interface

All metrics must implement a common interface.

```python
from abc import ABC, abstractmethod

class ScoringMetric(ABC):

    @property
    @abstractmethod
    def metric_id(self) -> str:
        pass

    @property
    @abstractmethod
    def direction(self) -> str:
        """Return 'minimize' or 'maximize'."""
        pass

    @abstractmethod
    def compute(self, y_true, y_pred) -> float:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass
```

---

# Forecasting Metrics

Examples:

- MAE
- RMSE
- MAPE
- SMAPE

All should implement ScoringMetric.

---

# Anomaly Metrics

Examples:

- Precision
- Recall
- F1 Score
- ROC AUC
- PR AUC

All should implement ScoringMetric.

---

# Plugin Discovery

Plugins are registered through registries at application startup.

Example:

```python
twin_registry.register(MechanicalTwin())
```

The registry is responsible for:

- discovery;
- validation;
- lookup;
- metadata retrieval.

See [Plugin Registry](plugin-registry.md) for the full specification.

---

# Twin Registry

```python
twin_registry.register(MechanicalTwin())
twin_registry.register(IndustrialPumpTwin())
```

The REST API automatically exposes all registered twins.

---

# Sensor Registry

```python
sensor_registry.register(PositionSensor())
sensor_registry.register(TemperatureSensor())
```

Sensors become reusable building blocks.

---

# Fault Registry

```python
fault_registry.register(SensorBiasFault())
fault_registry.register(IncreasedDampingFault())
```

Faults become reusable across multiple twins.

---

# Metadata Contract

Every plugin must implement a `metadata()` method returning a dict.

The key for the plugin's identifier must match the plugin's own id field (e.g. `sensor_id`, `fault_id`, `twin_id`, `metric_id`).

Example for a sensor:

```python
{
    "sensor_id": "temperature_sensor",
    "name": "Temperature Sensor",
    "version": "1.0.0",
    "description": "Basic temperature sensor"
}
```

Metadata is used by:

- APIs
- documentation
- UI components
- contest configuration

---

# Versioning

Plugins should support versioning.

Example:

```python
temperature_sensor:1.0
temperature_sensor:1.1
industrial_pump_twin:2.0
```

This allows reproducible contests.

---

# Compatibility Rules

A plugin must never modify the Core.

A plugin may depend on:

- EPIC Core
- Other plugin interfaces

A plugin must not depend on:

- Internal implementation details of other plugins

---

# Long-Term Objective

The plugin system should allow the creation of completely new domains by implementing interfaces.

Examples:

- Industrial process monitoring
- Smart manufacturing
- Robotics
- Biomedical monitoring
- Environmental sensing
- Network traffic analysis

without changing any EPIC infrastructure component.