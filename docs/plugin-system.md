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
    def create_initial_state(self):
        pass

    @abstractmethod
    def step(self, state, dt):
        pass

    @abstractmethod
    def get_sensors(self):
        pass

    @abstractmethod
    def get_faults(self):
        pass

    @abstractmethod
    def get_scenarios(self):
        pass

    @abstractmethod
    def metadata(self):
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
    def unit(self) -> str:
        pass

    @abstractmethod
    def observe(self, state):
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

    @abstractmethod
    def apply(self, state, dt):
        pass
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

Examples:

- bias
- drift
- stuck values
- excessive noise

The Core should not distinguish between categories.

---

# Scenario Interface

Scenarios define simulation conditions.

```python
from abc import ABC, abstractmethod

class Scenario(ABC):

    @property
    @abstractmethod
    def scenario_id(self):
        pass

    @abstractmethod
    def initialize(self):
        pass

    @abstractmethod
    def get_fault_schedule(self):
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
    def value(self, t):
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
    def metric_id(self):
        pass

    @abstractmethod
    def compute(self, y_true, y_pred):
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

Plugins should be registered through registries.

Example:

```python
registry.register(MyTwin())
```

or

```python
registry.register_class(MyTwin)
```

The registry is responsible for:

- discovery;
- validation;
- lookup;
- metadata retrieval.

---

# Twin Registry

```python
registry.register(MechanicalTwin())
registry.register(IndustrialPumpTwin())
```

The REST API should automatically expose all registered twins.

---

# Sensor Registry

```python
sensor_registry.register(PositionSensor)
sensor_registry.register(TemperatureSensor)
```

Sensors become reusable building blocks.

---

# Fault Registry

```python
fault_registry.register(BiasFault)
fault_registry.register(DriftFault)
```

Faults become reusable across multiple twins.

---

# Metadata Contract

Every plugin should expose metadata.

Example:

```python
{
    "id": "temperature_sensor",
    "name": "Temperature Sensor",
    "version": "1.0",
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