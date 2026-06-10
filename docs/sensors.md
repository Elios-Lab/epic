# Sensor Framework

Sensors are the only channel through which participants can observe a digital twin. A participant never has direct access to the twin's internal state or physical quantities — they always receive a sensor measurement, which may include noise, drift, latency, and other realistic degradations.

Sensor implementations live in `epic_sensors/` and are completely independent of any specific twin. A sensor can be applied to any twin that provides the physical quantity the sensor measures.

---

# Design Philosophy

A sensor in EPIC is independent of any specific twin: the only coupling between the two is the `PhysicalQuantity` it declares to measure, so a temperature sensor works equally well on a mechanical twin, an industrial pump, or a biomedical system. Every aspect of its measurement behavior — noise, drift, quantization, latency, saturation, probabilistic failures — is a constructor parameter, which makes the entire degradation pipeline configurable per contest without writing code. The pipeline is also deliberately transparent: the implementation documents exactly how the signal degrades, stage by stage, so that an organizer knows precisely what kind of challenge a given configuration produces.

The EPIC Core never knows what physical quantity a sensor measures. It only receives the final `float` from `sensor.observe()`.

---

# Physical Quantities

The decoupling between sensors and twins rests on a shared ontology of physical quantities — the *only* vocabulary the two kinds of plugin must agree on. A sensor declares the one quantity it measures through its `measured_quantity` property; a twin declares the set of quantities its latent state provides through `supported_quantities()` and answers `state.get_quantity(q)` with the current value, or `None` for quantities it does not model. The engine matches the two at contest creation and again at session start, so an incompatible sensor–twin combination can never be published, let alone run:

```python
twin_quantities = twin.supported_quantities()
for sensor in contest_sensors:
    if sensor.measured_quantity not in twin_quantities:
        raise EPICValidationError(...)
```

The canonical list is the `PhysicalQuantity` enum in `epic_core/quantities.py` — the code is the source of truth, exposed at runtime through the catalog API. It currently spans translational and rotational mechanics, thermodynamics, fluid dynamics, electrical quantities, vibration and acoustics, environmental quantities (humidity, CO₂, occupancy, illuminance), network/cyber metrics, and biomedical signals — deliberately broader than the built-in twins need, so future domains can plug in without touching the ontology.

Extending it is additive: a new member in the enum requires no other Core change, no modification to existing twins or sensors (a twin that does not model the new quantity simply returns `None`), and immediately allows new twin and sensor plugins to declare it.

---

# Package Structure

The sensor package is flat: one module per sensor, a shared base class, and a registration entry point.

```text
epic_sensors/
├── __init__.py
├── base.py              ← _BaseSensor: the full measurement pipeline
├── plugin.py            ← register() call for all sensors at startup
├── acceleration.py      ← AccelerationSensor   (LINEAR_ACCELERATION, m/s²)
├── co2_concentration.py ← CO2ConcentrationSensor (CO2_CONCENTRATION, ppm)
├── current.py           ← CurrentSensor        (CURRENT, A)
├── flow_rate.py         ← FlowRateSensor       (FLOW_RATE, m³/h)
├── humidity.py          ← HumiditySensor       (HUMIDITY, %RH)
├── occupancy.py         ← OccupancySensor      (OCCUPANCY, people)
├── position.py          ← PositionSensor       (LINEAR_POSITION, m)
├── power.py             ← PowerSensor          (POWER, W)
├── pressure.py          ← PressureSensor       (PRESSURE, bar)
├── rotational_speed.py  ← RotationalSpeedSensor (ROTATIONAL_SPEED, RPM)
├── temperature.py       ← TemperatureSensor    (TEMPERATURE, °C)
├── velocity.py          ← VelocitySensor       (LINEAR_VELOCITY, m/s)
├── vibration.py         ← VibrationSensor      (VIBRATION, mm/s)
└── voltage.py           ← VoltageSensor        (VOLTAGE, V)
```

Each concrete sensor is a thin declaration on top of `_BaseSensor`: it sets its identifier, display name, unit, measured quantity, and description, and inherits the entire measurement pipeline. Adding a new sensor for an already-supported quantity is therefore a file of a dozen lines.

---

# Responsibilities

A sensor has a narrow, well-defined job. It declares which physical quantity it measures through the `measured_quantity` property, reads that quantity from the simulation state via `state.get_quantity()`, pushes the value through its measurement pipeline, and returns a single scalar `float`.

Everything else is explicitly outside its scope. A sensor does not evolve state — that is the twin's job. It does not schedule or apply faults, manage contests, or score submissions. It does not even decide which twins it works with: compatibility is validated by the engine, which checks that the sensor's measured quantity is among the twin's supported quantities before a session starts.

---

# Sensor Interface

Every sensor must implement the `Sensor` abstract class defined in `epic_core/interfaces.py`. The interface requires `sensor_id`, `name`, `unit`, and `measured_quantity` as properties, plus the `observe(state, dt)` method that produces the measurement and a `metadata()` method that returns a dictionary used by the API, the documentation, the user interface, and contest configuration tooling.

A typical metadata payload looks like this:

```python
{
    "sensor_id": "temperature",
    "name": "Temperature Sensor",
    "unit": "°C",
    "measured_quantity": "temperature",
    "version": "1.0.0",
    "description": "Measures temperature in degrees Celsius",
}
```

---

# The Measurement Pipeline

Every call to `observe()` reads the clean latent value from the twin's state and transforms it through a fixed sequence of stages, each controlled by a constructor parameter and each inactive by default:

```text
latent value
    → gain                 (gain)
    → offset               (bias)
    → Gaussian noise       (noise_std)
    → accumulated drift    (drift_rate)
    → saturation           (min_value, max_value)
    → quantization         (quantization)
    → latency              (latency_steps)
    → false reading        (p_false_reading)
    → outlier injection    (p_outlier)
    → measurement
```

The first stages model calibration and electronics. *Gain* multiplies the latent value, modeling scale error; *bias* adds a constant offset, useful both as a calibration parameter and as a way to simulate a miscalibrated instrument. *Noise* adds a zero-mean Gaussian sample with standard deviation `noise_std`, the most common way to make a forecasting task non-trivial. *Drift* accumulates over time: at every observation the internal drift state grows by `drift_rate × dt` and is added to the measurement, so a sensor with a small positive drift rate reads progressively higher over the course of a long contest — exactly like a real instrument losing calibration.

The next stages model the physical limits of an instrument. *Saturation* clips the measurement to the `[min_value, max_value]` operating range, the way a thermometer rated for −40 °C to 125 °C simply cannot report values outside that interval. *Quantization* rounds the measurement to the nearest multiple of the configured resolution, so a temperature sensor with `quantization=0.1` reports 21.3 rather than 21.2974. *Latency* delays the reported value by a configurable number of steps using an internal buffer: with `latency_steps=3`, the participant sees at each step the measurement taken three steps earlier.

The final stages are probabilistic failure modes, important for anomaly-detection-style challenges. With probability `p_false_reading` per observation, the sensor discards the true measurement entirely and returns a random value drawn from its operating range — a wrong reading indistinguishable from a real one. With probability `p_outlier`, an extreme spike of about ten noise standard deviations is added on top of the measurement. A contest that sets `p_false_reading=0.02` will corrupt roughly two percent of observations, which is enough to defeat naive models without making the stream useless.

These failure modes are intrinsic sensor properties, configured as parameters of the measurement pipeline. They are deliberately *not* `FaultDescriptor` objects: physical faults belong to the twin and alter the latent state itself, while sensor failures only corrupt the observation of an otherwise healthy state. The fault side of this distinction is documented in [Digital Twins](digital-twins.md). Additional failure modes found in real instruments — stuck-at values, dropout (missing readings), step changes in noise level — follow the same philosophy and are natural candidates for future pipeline parameters.

---

# Ground Truth Is Not Affected

The pipeline corrupts only what participants see. The engine separately records the clean latent value (`state.get_quantity()`) as ground truth for every evaluation-phase observation, so scoring can compare forecasts against the true physical signal rather than against the corrupted measurement. The organizer chooses which reference to score against through the `score_against` task configuration field, as described in [Scoring](scoring.md).

---

# Configuration and Instantiation

The registry holds one **prototype** instance per sensor type, registered at application startup. The prototype is used exclusively for discovery and metadata retrieval, for validating sensor–twin compatibility, and as a type reference during session initialization. It never performs observations for a contest.

When a contest session starts, the engine obtains a fresh sensor instance through the `Sensor.configure()` contract, applying the contest's `sensor_configs` overrides:

```python
configured_sensor = registered_sensor.configure(overrides, rng)   # fresh instance, independent per session
```

`configure()` is part of the `Sensor` interface and is the formal configuration mechanism: the engine never calls a sensor constructor directly. The default implementation reconstructs the sensor through its own class with the overrides as constructor keyword arguments, injecting the per-session RNG when the constructor declares an `rng` parameter; a sensor with a different configuration mechanism can override the method.

This mirrors how digital twins are instantiated. Each contest session gets its own independent sensor instances, carrying their own drift accumulator, latency buffer, and any other stateful pipeline components, so two concurrent contests using the same sensor type never share state.

Randomness is injected the same way: the engine passes a per-session `random.Random` instance through the `rng` constructor parameter (it is the one key of `sensor_configs` that is never user-configurable). All stochastic pipeline stages — noise, false readings, outliers — draw from this generator, which is what makes seeded sessions reproducible even when several contests run concurrently. A sensor built without an `rng` falls back to the module-level generator.

In a contest configuration this looks like:

```json
"sensor_configs": [
    {"sensor_id": "position", "noise_std": 0.002},
    {"sensor_id": "temperature", "noise_std": 0.05, "drift_rate": 0.001}
]
```

Every key other than `sensor_id` is passed to the sensor constructor, so the full pipeline described above is reachable from configuration alone.

---

# Sampling

In the current implementation all sensors of a contest are sampled together at the contest's `sampling_rate_hz` — the engine calls `observe()` on every configured sensor at every simulation step. Heterogeneous per-sensor rates (a position sensor at 100 Hz next to a temperature sensor at 1 Hz) and asynchronous sampling are planned future extensions; they will be expressed as additional sensor configuration parameters, not as changes to the sensor interface.

---

# Beyond Scalar Sensors

All built-in sensors are scalar: one quantity, one `float` per observation. The framework is expected to grow toward other categories over time — vector sensors such as three-axis accelerometers, high-frequency time-series sensors such as raw vibration or ECG waveforms, and event sensors such as switches and alarms. These will require extensions to the observation payload and possibly to storage and streaming, which is why they are kept out of the minimal `Sensor` interface today.

The sensor library itself grows with the twin catalog. The current fourteen sensors cover every quantity exposed by the five built-in twins except torque; obvious next additions are a torque sensor for the electric motor and domain packs (biomedical, cyber-physical, environmental) as new twins arrive. A new sensor for an existing quantity requires no Core change — implement, register, done.

---

# Design Requirement

A sensor must be reusable across multiple digital twins without modification. The temperature sensor is the canonical test: it works today on the mass-spring-damper, the industrial pump, the electric motor, the rotating machinery, and the smart building, because each of those twins exposes `TEMPERATURE` among its supported quantities. If a proposed sensor design only works with one specific twin, the coupling is a design error — either the shared quantity belongs in the `PhysicalQuantity` ontology, or the logic belongs inside the twin.

This requirement is a key measure of success for the Sensor Framework.
