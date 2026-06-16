# EPIC Twins

This directory contains the built-in digital twins. Each twin is self-contained: it owns state evolution, fault activation, and fault effects. The platform discovers twins through the plugin registry and exposes their runtime metadata through the catalog API.

## Built-in Twins and Sensors

Digital twins implement the DigitalTwin interface and the available twins are listed in the catalog. Each twin has a unique id, a human-friendly name, and a set of supported physical quantities and faults.

| Twin ID              | System | Quantities | Faults |
|----------------------|---|---|---|
| `mass_spring_damper` | Mechanical oscillator | `position`, `velocity`, `acceleration`, `temperature` | `increased_damping`, `reduced_stiffness`, `increased_friction` |
| `industrial_pump` | Centrifugal pump | `flow_rate`, `pressure`, `temperature`, `vibration` | `cavitation`, `bearing_wear`, `filter_clog` |
| `electric_motor` | Three-phase induction motor | `current`, `voltage`, `rotational_speed`, `temperature` | `overheating`, `bearing_fault`, `voltage_imbalance` |
| `rotating_machinery` | Shaft and gearbox | `rotational_speed`, `vibration`, `temperature`, `power` | `unbalance`, `misalignment`, `gear_tooth_wear` |
| `smart_building` | HVAC-managed floor | `temperature`, `humidity`, `co2_concentration`, `occupancy` | `hvac_failure`, `sensor_drift`, `occupancy_spike` |

The runtime source of truth is the catalog API:

```text
GET /api/v1/catalog
GET /api/v1/catalog/{twin_id}
```

Registered scalar sensors:

| Sensor ID | Unit | Typical Use |
|---|---|---|
| `position` | m | Mechanical displacement |
| `velocity` | m/s | Linear velocity |
| `acceleration` | m/s2 | Linear acceleration |
| `temperature` | deg C | Thermal behaviour |
| `flow_rate` | m3/h | Pump flow |
| `pressure` | bar | Fluid pressure |
| `vibration` | mm/s | Machinery health |
| `current` | A | Motor current |
| `voltage` | V | Electrical supply |
| `rotational_speed` | RPM | Shaft or motor speed |
| `power` | W | Mechanical or electrical power |
| `humidity` | %RH | Building environment |
| `co2_concentration` | ppm | Indoor air quality |
| `occupancy` | people | Building load |

Each sensor supports the same measurement-pipeline parameters:

| Parameter | Effect |
|---|---|
| `noise_std` | Gaussian noise. |
| `gain` | Multiplicative calibration factor. |
| `bias` | Additive offset. |
| `drift_rate` | Time-dependent drift. |
| `min_value`, `max_value` | Saturation bounds. |
| `quantization` | Rounding step. |
| `latency_steps` | Delayed output. |
| `p_false_reading` | Probability of replacing the reading with a false value. |
| `p_outlier` | Probability of injecting a large outlier. |

The registry stores sensor prototypes. The engine creates a fresh configured
sensor instance for each session so drift, buffers, and random state never leak
between contests.

## Extending EPIC

### Add a Digital Twin

Implement `DigitalTwin`:

```python
class DigitalTwin:
    twin_id: str
    name: str
    def configure(self, initial_conditions: dict | None, fault_schedule: list[dict]) -> SimulationState: ...
    def step(self, state: SimulationState, dt: float) -> SimulationState: ...
    def get_active_faults(self) -> list[dict]: ...
    def supported_quantities(self) -> set[PhysicalQuantity]: ...
    def get_faults(self) -> list[FaultDescriptor]: ...
    def metadata(self) -> dict: ...
```

Register it:

```python
import epic.core.registry as registry_module
from my_twin import MyTwin

registry_module.twin_registry.register(MyTwin())
```

### Add a Sensor

Implement `Sensor`, declare `measured_quantity`, and register it with
`sensor_registry`. If the quantity already exists in `PhysicalQuantity`, no Core
change is needed. New quantities belong in `epic/core/quantities.py`.

### Add a Metric

Implement `ScoringMetric` and register it with `metric_registry`:

```python
class MyMetric(ScoringMetric):
    metric_id = "my_metric"
    direction = "minimize"
    def compute(self, y_true, y_pred) -> float: ...
    def metadata(self) -> dict: ...
```

### Add a Task Type

Implement `TaskEvaluator` and register it with `task_evaluator_registry`. A task
evaluator owns payload validation, metric application, and the leaderboard
ranking value for one task type.
