# Sensor Framework

> Related: [Physical Quantities](quantities.md) · [Digital Twins](digital-twins.md) · [Simulation Engine](simulation-engine.md)

Sensors are the only channel through which participants can observe a digital twin. A participant never has direct access to the twin's internal state or physical quantities — they always receive a sensor measurement, which may include noise, drift, latency, and other realistic degradations.

Sensor implementations live in `epic_sensors/` and are completely independent of any specific twin. A sensor can be applied to any twin that provides the physical quantity the sensor measures.

---

# Package Structure

```text
epic_sensors/
├── __init__.py
├── registry.py          ← register() call for all sensors at startup
├── linear/
│   ├── position.py      ← PositionSensor  (LINEAR_POSITION)
│   ├── velocity.py      ← VelocitySensor  (LINEAR_VELOCITY)
│   └── acceleration.py  ← AccelerationSensor (LINEAR_ACCELERATION)
├── thermal/
│   └── temperature.py   ← TemperatureSensor (TEMPERATURE)
└── mechanical/
    └── pressure.py      ← PressureSensor  (PRESSURE)  [future]
```

---

# Design Philosophy

A sensor is:

- **Independent from a specific twin** — coupled only through `PhysicalQuantity`
- **Reusable across domains** — a `TemperatureSensor` works for a mechanical twin, an industrial pump, or a biomedical system
- **Configurable** — noise, drift, quantization, latency, saturation are constructor parameters
- **Honest about its limitations** — the measurement pipeline documents exactly how the signal degrades

The EPIC Core never knows what physical quantity a sensor measures. It only receives the final `float` from `sensor.observe()`.

---

# Sensor Responsibilities

A sensor is responsible for:

- Declaring which physical quantity it measures (`measured_quantity`)
- Reading that quantity from the state via `state.get_quantity()`
- Applying the measurement pipeline
- Producing a scalar `float` measurement

A sensor is not responsible for:

- State evolution
- Fault scheduling
- Contest management
- Scoring
- Deciding which twin it works with (that is the engine's job, via compatibility validation)

---

# Sensor Interface

Every sensor must implement the `Sensor` abstract class defined in `epic_core/interfaces.py`.

The interface requires implementing: `sensor_id`, `name`, `unit`, `measured_quantity`, `observe(state, dt)`, and `metadata()`.

---

# Measurement Pipeline

Conceptually, every sensor implements:

```text
Latent Variable
        ↓
Gain
        ↓
Bias
        ↓
Noise
        ↓
Saturation
        ↓
Quantization
        ↓
Filtering
        ↓
Sensor Fault
        ↓
Measurement
```

Not all stages need to be active.

The pipeline should be configurable.

---

# Sensor Metadata

Every sensor must expose metadata.

Example:

```python
{
    "sensor_id": "temperature_sensor",
    "name": "Temperature Sensor",
    "unit": "°C",
    "version": "1.0.0"
}
```

Metadata is used by:

- APIs
- Documentation
- User Interfaces
- Contest configuration

---

# Basic Sensor Parameters

All sensors should support:

```python
sensor_id: str

unit: str

sampling_rate_hz: float

gain: float

bias: float

noise_std: float

resolution: float

min_value: float

max_value: float
```

These parameters provide a generic abstraction that applies to many domains.

---

# Sampling Rate

A sensor may operate at a specific frequency.

Example:

```text
Position Sensor:
100 Hz

Temperature Sensor:
1 Hz
```

The simulation engine should support heterogeneous sensor rates.

Future implementations may support asynchronous sampling.

---

# Gain

Gain scales the measured quantity.

Example:

```text
measurement = gain * value
```

---

# Bias

Bias adds a constant offset.

Example:

```text
measurement = value + bias
```

Bias is useful both as a calibration parameter and as a fault mechanism.

---

# Noise

Noise models measurement uncertainty.

Initial implementation:

```text
Gaussian Noise
```

Example:

```python
measurement += N(0, sigma)
```

Future implementations may support:

- Uniform noise
- Laplacian noise
- Colored noise
- Shot noise
- Quantization noise

---

# Saturation

Sensors may have finite operating ranges.

Example:

```text
Temperature Sensor:
[-40°C, 125°C]
```

Values outside the range are clipped.

```python
measurement = clip(value)
```

---

# Resolution

Sensors may have limited precision.

Example:

```text
Resolution = 0.1°C
```

Observed values are quantized.

```python
measurement = round(value / resolution) * resolution
```

---

# Filtering

Many real sensors behave as low-pass filters.

Example:

```text
True Temperature:
changes instantly

Measured Temperature:
changes gradually
```

Future versions should support:

- Low-pass filters
- High-pass filters
- Band-pass filters

---

# Latency

Sensors may introduce delays.

Example:

```text
Real Event
      ↓
Delay
      ↓
Measurement
```

Latency should be optional.

---

# Drift

Drift represents slow changes in calibration.

Example:

```text
Day 1:
+0.0°C

Day 30:
+1.5°C
```

Future versions should support:

- Linear drift
- Random walk drift
- Thermal drift

---

# Sensor Faults

Sensors themselves may fail.

These failures are important for anomaly detection challenges.

Examples:

- Bias
- Drift
- Stuck value
- Increased noise
- Dropout
- Saturation

---

# Probabilistic Failure Modes

Sensor failures — stuck values, false readings, outliers, dropout — are modelled as sensor parameters, not as Fault objects. They are part of the measurement pipeline:

```python
# Constructor parameters
p_false_reading: float = 0.0   # probability of returning a random wrong value
p_outlier: float = 0.0         # probability of an extreme spike
p_dropout: float = 0.0         # probability of returning NaN (missing data)
outlier_scale: float = 10.0    # how many std deviations the outlier spans
```

These are off by default. When a contest uses a sensor configured with `p_false_reading=0.02`, 2% of observations will be wrong values indistinguishable from real readings — a realistic challenge for anomaly detection tasks.

---

# Stuck Sensor

The sensor remains frozen.

Example:

```text
True Value:
10
12
15
18

Observed Value:
10
10
10
10
```

---

# Increased Noise

Variance increases significantly.

Example:

```text
Normal:
σ = 0.1

Fault:
σ = 2.0
```

---

# Dropout

Measurements disappear.

Example:

```text
10.2
10.3
null
null
10.4
```

Useful for realistic streaming challenges.

---

# Sensor Categories

The framework should support many sensor categories.

---

## Scalar Sensors

Return a single value.

Examples:

- Temperature
- Pressure
- Humidity
- Voltage

---

## Vector Sensors

Return multiple values.

Examples:

- Accelerometer
- Gyroscope
- Magnetic Field Sensor

Example:

```json
{
  "x": 0.1,
  "y": 0.2,
  "z": -0.3
}
```

---

## Time-Series Sensors

Generate signals at high frequency.

Examples:

- Vibration
- Audio
- ECG

These may require specialized storage and streaming.

---

## Event Sensors

Generate events rather than continuous measurements.

Examples:

- Switches
- Alarms
- Network Events

---

# Sensor Registry

Sensors should be discoverable through a registry.

Example:

```python
sensor_registry.register(PositionSensor())

sensor_registry.register(TemperatureSensor())
```

The registry should provide:

- Discovery
- Validation
- Metadata retrieval

---

# First EPIC Sensors

The first implementation should include:

```text
Position Sensor

Velocity Sensor

Acceleration Sensor

Temperature Sensor
```

These are sufficient for the first mechanical twin.

---

# Future Sensor Library

Potential future sensors:

## Industrial

- Pressure Sensor
- Flow Sensor
- Vibration Sensor
- Current Sensor
- Voltage Sensor

## Environmental

- Humidity Sensor
- Air Quality Sensor
- Wind Sensor

## Biomedical

- ECG Sensor
- Heart Rate Sensor
- SpO₂ Sensor

## Cyber Systems

- Packet Rate Sensor
- CPU Utilization Sensor
- Memory Usage Sensor

---

# Data Representation

Measurements should be represented as JSON-compatible values.

Example:

```json
{
  "temperature": 25.4,
  "pressure": 1.2
}
```

The API layer must not assume fixed sensor names.

---

# Design Requirement

A sensor should be reusable across multiple digital twins.

For example:

```text
Temperature Sensor
```

should be usable in:

- Industrial Pump Twin
- Electric Motor Twin
- Smart Building Twin
- Biomedical Twin

without modification.

This requirement is a key measure of success for the Sensor Framework.