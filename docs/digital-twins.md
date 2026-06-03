# Digital Twin Development Guide

> Related: [Plugin System](plugin-system.md) — canonical interfaces · [Sensors](sensors.md) · [Faults](faults.md) · [API Specification](api-specification.md)

Digital twins are the core simulation components of EPIC.

A digital twin represents a dynamic system that evolves over time and can be observed through sensors.

Examples include:

- Mechanical systems
- Industrial pumps
- Electric motors
- Manufacturing systems
- Smart buildings
- Power systems
- Environmental monitoring systems
- Biomedical systems
- Networked systems

The EPIC Core must remain independent from all of these domains.

A digital twin is therefore implemented as a plugin.

---

# Design Philosophy

A digital twin should model:

1. An internal latent state
2. State evolution dynamics
3. Observable sensors
4. Fault mechanisms
5. Scenarios

Participants should generally observe only the sensor outputs.

The latent state remains hidden.

---

# Digital Twin Responsibilities

Every digital twin must:

- Define its latent state
- Define state evolution rules
- Register sensors
- Register faults
- Register scenarios
- Expose metadata

A digital twin must not:

- Manage contests
- Manage users
- Perform authentication
- Compute leaderboards
- Manage submissions

Those responsibilities belong to EPIC Core.

---

# Digital Twin Interface

Every twin must implement the `DigitalTwin` abstract class defined in [Plugin System](plugin-system.md).

The interface requires implementing: `twin_id`, `name`, `create_initial_state(initial_conditions)`, `step(state, dt) -> SimulationState`, `get_sensors() -> list[Sensor]`, `get_faults() -> list[Fault]`, `get_scenarios() -> list[Scenario]`, and `metadata()`.

---

# Twin Metadata

Each twin must expose metadata.

Example:

```python
{
    "twin_id": "mechanical_system",
    "name": "Mechanical System",
    "version": "1.0.0",
    "description": "Simple mass-spring-damper example"
}
```

Metadata is used by:

- REST APIs
- Documentation
- Contest configuration
- User interfaces

---

# Latent State

The latent state represents the true state of the system.

Example:

```python
@dataclass
class MechanicalState:

    position: float

    velocity: float

    acceleration: float

    temperature: float
```

The latent state should never be exposed directly unless explicitly enabled for training scenarios.

---

# State Evolution

Each digital twin must implement a state evolution function.

Conceptually:

```python
new_state = twin.step(current_state, dt)
```

The function should:

1. Compute system dynamics
2. Apply operating profiles
3. Apply active faults
4. Update state variables

The returned state becomes the next simulation state.

---

# Sensors

Sensors observe the latent state.

The twin should register sensors during initialization.

Example:

```python
self.sensors = [
    PositionSensor(),
    VelocitySensor(),
    TemperatureSensor()
]
```

Sensors should be independent reusable components.

A twin should compose sensors rather than implement measurement logic directly.

---

# Faults

Faults introduce abnormal behaviour.

Example:

```python
self.faults = [
    IncreasedDampingFault(),
    SensorBiasFault()
]
```

Faults should also be reusable components.

A fault should not be tightly coupled to a single twin whenever possible.

---

# Scenarios

A scenario defines how the twin is used.

Typical responsibilities:

- Initial conditions
- Operating profile
- Active faults
- Fault schedule
- Environment configuration

Example:

```python
normal_operation

sensor_bias

increased_damping

intermittent_disturbance
```

---

# Scenario Scheduling

Scenarios may activate faults at specific times.

Example:

```text
0s   -> Normal operation

50s  -> Sensor bias begins

120s -> Increased damping begins
```

This allows realistic anomaly generation.

---

# Operating Profiles

An operating profile describes system inputs over time.

Examples:

- Constant input
- Sinusoidal input
- Random excitation
- Piecewise operating modes

Interface:

```python
profile.value(t)
```

The twin should use the profile to generate realistic operating conditions.

---

# Digital Twin Lifecycle

A simulation session typically follows:

```text
Create State
      ↓
Initialize Scenario
      ↓
Simulation Loop
      ↓
Apply Dynamics
      ↓
Apply Faults
      ↓
Generate Observations
      ↓
Store Results
      ↓
End Session
```

---

# First Reference Twin

The first EPIC twin should be intentionally simple.

Recommended model:

## Mass-Spring-Damper System

State variables:

```text
position
velocity
acceleration
temperature
```

System parameters:

```text
mass
stiffness
damping
```

This system provides:

- Continuous dynamics
- Forecasting challenges
- Fault injection opportunities
- Minimal implementation complexity

---

# Example State Update

Conceptual model:

```text
m*x'' + c*x' + k*x = F(t)
```

Where:

```text
m = mass
c = damping
k = stiffness
F = external force
```

The exact implementation is left to the twin.

---

# Example Faults

Suitable faults for the first twin:

## Increased Damping

Gradually increase damping coefficient.

Effects:

- Reduced oscillation amplitude
- Slower response

---

## Reduced Stiffness

Gradually decrease stiffness.

Effects:

- Lower natural frequency
- Different oscillation pattern

---

## Increased Friction

Adds energy dissipation.

Effects:

- Faster decay
- Increased temperature

---

## Sensor Bias

Adds constant offset.

Effects:

- Observation error
- No physical change

---

## Noisy Sensor

Increases observation variance.

Effects:

- Reduced signal quality

---

# Data Visibility

Different contest modes expose different information.

## Training

May expose:

- Sensor observations
- Labels
- Fault metadata
- Latent state (optional)

---

## Validation

Usually exposes:

- Sensor observations

May expose limited labels.

---

## Test

Exposes:

- Sensor observations only

No hidden information should be available.

---

# Twin Registration

A twin becomes available after registration.

Example:

```python
registry.register(MechanicalTwin())
```

After registration, the platform should automatically expose:

```text
GET /api/v1/twins
```

and related endpoints.

No API changes should be required.

---

# Versioning

Each twin should be versioned.

Example:

```text
mechanical_system:1.0.0
industrial_pump:2.1.0
```

Version information is important for:

- Reproducibility
- Benchmarking
- Research experiments

---

# Future Digital Twins

Potential future twins include:

## Industrial Pump

Sensors:

- Pressure
- Flow
- Vibration
- Temperature

Faults:

- Cavitation
- Bearing wear
- Filter obstruction

---

## Electric Motor

Sensors:

- Current
- Voltage
- Temperature
- RPM

Faults:

- Overheating
- Bearing degradation
- Electrical faults

---

## Smart Building

Sensors:

- Temperature
- Humidity
- Occupancy

Faults:

- HVAC failures
- Sensor failures

---

## Biomedical Monitoring

Sensors:

- ECG
- Heart rate
- SpO₂

Faults:

- Arrhythmias
- Sensor artifacts

---

# Design Requirement

A new digital twin should be implementable by:

1. Defining a state model
2. Implementing dynamics
3. Registering sensors
4. Registering faults
5. Registering scenarios

without modifying any EPIC Core component.

This requirement is the primary measure of success for the EPIC architecture.