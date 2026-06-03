# Fault Framework

> Related: [Plugin System](plugin-system.md) — canonical `Fault` and `SensorFault` interfaces · [Sensors](sensors.md) · [Digital Twins](digital-twins.md)

The Fault Framework provides a generic mechanism for introducing abnormal conditions into a digital twin.

Faults are one of the primary sources of machine learning challenges in EPIC.

They create deviations from normal behavior that participants must detect, classify, forecast or anticipate.

The framework must support a wide range of application domains while remaining independent from any specific physical system.

Examples include:

- Mechanical wear
- Electrical failures
- Sensor degradation
- Environmental disturbances
- Communication failures
- Software anomalies

The EPIC Core must treat all faults generically.

---

# Design Philosophy

A fault is an object that modifies the behavior of a system.

A fault may affect:

- The latent state
- The system parameters
- The operating profile
- The sensor outputs

The platform should not assume any particular fault type.

---

# Objectives

The Fault Framework must support:

- Fault injection
- Fault scheduling
- Fault evolution
- Fault composition
- Fault metadata
- Fault reproducibility

The same fault should be reusable across multiple digital twins whenever possible.

---

# Fault Interface

All faults must implement the `Fault` abstract class defined in [Plugin System](plugin-system.md).

The interface requires implementing: `fault_id`, `name`, `current_severity`, `activate(initial_severity)`, `deactivate()`, `apply(state, dt)`, and `metadata()`.

Faults that corrupt sensor measurements rather than the latent state must extend `SensorFault` instead of `Fault` directly, and implement `target_sensor_ids` and `apply_to_measurement(measurement)`. See [Plugin System](plugin-system.md) for the full interface definitions and the simulation engine's application order.

---

# Fault Metadata

Every fault should expose metadata.

Example:

```python
{
    "fault_id": "increased_damping",
    "name": "Increased Damping",
    "version": "1.0.0",
    "description": "Gradual increase in damping coefficient"
}
```

Metadata is used for:

- APIs
- Documentation
- Contest configuration
- Scenario generation

---

# Fault Categories

Faults can be classified according to what they affect.

---

## State Faults

Modify latent state variables.

Examples:

- Increased temperature
- Accelerated wear
- Battery discharge

Example:

```python
state.temperature += 0.5
```

---

## Parameter Faults

Modify model parameters.

Examples:

- Increased damping
- Reduced stiffness
- Reduced efficiency

Example:

```python
state.damping *= 1.05
```

---

## Sensor Faults

Modify observations.

Examples:

- Bias
- Drift
- Increased noise
- Stuck values

These are typically applied after the measurement process.

---

## Environmental Faults

Modify operating conditions.

Examples:

- External disturbances
- Ambient temperature changes
- Communication disruptions

---

# Fault Lifecycle

Every fault follows a lifecycle.

```text
INACTIVE
    ↓
ACTIVE
    ↓
EVOLVING
    ↓
TERMINATED
```

Some faults may remain active indefinitely.

Others may be temporary.

---

# Fault Activation

Faults may activate:

- Immediately
- At a scheduled time
- Randomly
- Based on state conditions

Example:

```text
Activate after 100 seconds
```

or

```text
Activate when temperature > 80°C
```

---

# Fault Scheduling

Fault scheduling is controlled by scenarios.

Example:

```text
0s      Normal operation
120s    Increased damping begins
300s    Sensor bias begins
```

The fault itself should not decide when it starts.

The scenario should.

---

# Fault Evolution

Faults may evolve over time.

Three fundamental modes should be supported.

---

## Sudden Faults

Immediate change.

Example:

```text
Bearing breaks
```

Behavior:

```text
Normal
↓
Faulty
```

---

## Gradual Faults

Progressive degradation.

Example:

```text
Bearing wear
```

Behavior:

```text
Healthy
↓
Slight degradation
↓
Moderate degradation
↓
Severe degradation
```

---

## Intermittent Faults

Appear and disappear.

Example:

```text
Loose electrical connection
```

Behavior:

```text
Normal
↓
Fault
↓
Normal
↓
Fault
```

---

# Fault Severity

Faults may have severity levels.

Example:

```python
severity = 0.0
```

means:

```text
No fault
```

while:

```python
severity = 1.0
```

means:

```text
Maximum severity
```

Severity can evolve over time.

---

# Fault Composition

Multiple faults may coexist.

Example:

```text
Bearing Wear
+
Sensor Bias
+
External Disturbance
```

The framework should allow fault composition.

---

# Fault Composition Example

```python
faults = [
    BearingWear(),
    SensorBias(),
    ExternalDisturbance()
]
```

All active faults are applied sequentially.

---

# Fault Labels

During training, labels may be exposed.

Example:

```json
{
  "is_anomaly": true,
  "fault_type": "bearing_wear"
}
```

---

# Hidden Faults

During evaluation:

```text
Validation
Test
```

fault labels may be hidden.

Participants must infer them from observations.

---

# Fault Registry

Faults should be discoverable.

Example:

```python
fault_registry.register(IncreasedDampingFault())

fault_registry.register(SensorBiasFault())
```

The registry enables:

- Discovery
- Metadata retrieval
- Validation

---

# Reference Faults

The first EPIC implementation should include a minimal set of reusable faults.

---

## Increased Damping

Target:

```text
Mechanical Twin
```

Effect:

```text
Higher damping coefficient
```

Expected observations:

- Reduced oscillation amplitude
- Slower dynamics

---

## Reduced Stiffness

Target:

```text
Mechanical Twin
```

Effect:

```text
Lower stiffness coefficient
```

Expected observations:

- Lower oscillation frequency
- Different transient response

---

## Increased Friction

Target:

```text
Mechanical Twin
```

Effect:

```text
Additional energy dissipation
```

Expected observations:

- Faster decay
- Temperature increase

---

## Sensor Bias

Target:

```text
Any Sensor
```

Effect:

```text
measurement += bias
```

Expected observations:

- Persistent offset

---

## Increased Noise

Target:

```text
Any Sensor
```

Effect:

```text
noise_std *= factor
```

Expected observations:

- Reduced signal quality

---

## Stuck Sensor

Target:

```text
Any Sensor
```

Effect:

```text
Measurement frozen
```

Expected observations:

- Constant value

---

# Fault Hierarchy

Recommended implementation:

```python
Fault                        # apply(state, dt) — modifies latent state or parameters
├── StateFault               # e.g. temperature increase, accelerated wear
├── ParameterFault           # e.g. increased damping, reduced stiffness
├── SensorFault              # apply_to_measurement(measurement) — corrupts observations
│   ├── BiasFault
│   ├── DriftFault
│   ├── StuckSensorFault
│   └── IncreasedNoiseFault
└── EnvironmentalFault       # e.g. external disturbances, ambient changes
```

`SensorFault` overrides `apply(state, dt)` as a no-op and adds `apply_to_measurement()`. All subclasses are registered in the same fault registry and participate in the same lifecycle. The simulation engine distinguishes the application point using `isinstance(fault, SensorFault)` — no other Core change is required when new fault types are added.

---

# Fault Persistence

Fault metadata should be persisted.

Example:

```python
{
    "fault_id": "sensor_bias",
    "start_time": 120.0,
    "severity": 0.4
}
```

This supports:

- Reproducibility
- Auditing
- Research experiments

---

# Contest Usage

Faults are the foundation of several EPIC tasks.

Examples:

## Anomaly Detection

Detect the presence of faults.

---

## Fault Classification

Identify the fault type.

---

## Fault Forecasting

Predict future fault evolution.

---

## Remaining Useful Life

Estimate time-to-failure.

---

# Future Fault Library

Potential future additions:

## Industrial

- Bearing Wear
- Cavitation
- Filter Obstruction
- Shaft Misalignment
- Motor Overheating

---

## Electrical

- Voltage Sag
- Current Imbalance
- Insulation Degradation

---

## Environmental

- Sensor Contamination
- Humidity Drift

---

## Network

- Packet Loss
- Latency Spikes
- Congestion Events

---

## Biomedical

- Motion Artifacts
- Sensor Detachment
- Arrhythmias

---

# Design Requirement

A fault should be reusable.

For example:

```text
Sensor Bias
```

should work identically for:

- Position Sensors
- Temperature Sensors
- Pressure Sensors
- ECG Sensors

without modifications.

The ability to reuse fault models across domains is a key measure of success for the EPIC Fault Framework.