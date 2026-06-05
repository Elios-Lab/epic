# Physical Quantities

> Related: [Plugin System](plugin-system.md) · [Sensors](sensors.md) · [Digital Twins](digital-twins.md)

EPIC uses a shared ontology of physical quantities to decouple sensors from digital twins. A sensor declares which physical quantity it measures; a twin declares which physical quantities its latent state provides. The engine matches them at session start.

This is the only shared vocabulary that must be agreed upon between a sensor plugin and a twin plugin. No other coupling exists between the two.

---

# PhysicalQuantity

The canonical list of physical quantities lives in `epic_core/quantities.py`:

```python
from enum import Enum

class PhysicalQuantity(Enum):

    # Translational mechanics
    LINEAR_POSITION     = "linear_position"      # m
    LINEAR_VELOCITY     = "linear_velocity"      # m/s
    LINEAR_ACCELERATION = "linear_acceleration"  # m/s²

    # Rotational mechanics
    ANGULAR_POSITION    = "angular_position"     # rad
    ANGULAR_VELOCITY    = "angular_velocity"     # rad/s
    ANGULAR_ACCELERATION = "angular_acceleration" # rad/s²

    # Thermodynamics
    TEMPERATURE         = "temperature"          # °C
    HEAT_FLUX           = "heat_flux"            # W/m²

    # Fluid dynamics
    PRESSURE            = "pressure"             # Pa
    FLOW_RATE           = "flow_rate"            # m³/s
    FLUID_LEVEL         = "fluid_level"          # m

    # Electrical
    CURRENT             = "current"              # A
    VOLTAGE             = "voltage"              # V
    POWER               = "power"                # W
    RESISTANCE          = "resistance"           # Ω

    # Vibration / acoustics
    VIBRATION           = "vibration"            # m/s²  (broadband)
    SOUND_PRESSURE      = "sound_pressure"       # Pa

    # Environmental
    HUMIDITY            = "humidity"             # % relative
    ILLUMINANCE         = "illuminance"          # lux

    # Network / cyber
    PACKET_RATE         = "packet_rate"          # packets/s
    LATENCY             = "latency"              # ms
    CPU_UTILIZATION     = "cpu_utilization"      # %

    # Biomedical
    HEART_RATE          = "heart_rate"           # bpm
    BLOOD_OXYGEN        = "blood_oxygen"         # % SpO₂
    ECG_SIGNAL          = "ecg_signal"           # mV
```

---

# How Twins Expose Quantities

Every twin's state class must implement:

```python
def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
    """
    Return the current value for a physical quantity.
    Return None if the twin's state does not model this quantity.
    """
```

Example for the mechanical twin:

```python
def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
    return {
        PhysicalQuantity.LINEAR_POSITION:     self.position,
        PhysicalQuantity.LINEAR_VELOCITY:     self.velocity,
        PhysicalQuantity.LINEAR_ACCELERATION: self.acceleration,
        PhysicalQuantity.TEMPERATURE:         self.temperature,
    }.get(quantity)
```

---

# How Sensors Declare Their Quantity

Every sensor declares one measured quantity:

```python
class PositionSensor(Sensor):
    @property
    def measured_quantity(self) -> PhysicalQuantity:
        return PhysicalQuantity.LINEAR_POSITION
```

The sensor's `observe()` method reads from `state.get_quantity(self.measured_quantity)` and applies its pipeline (noise, drift, quantization, latency) on top.

---

# Compatibility Validation

Before a simulation session starts, the engine verifies that every sensor selected for the contest can be satisfied by the twin's state:

```python
twin_quantities = twin.supported_quantities()
for sensor in contest_sensors:
    if sensor.measured_quantity not in twin_quantities:
        raise EPICValidationError(
            f"Sensor '{sensor.sensor_id}' measures "
            f"'{sensor.measured_quantity.value}' but twin "
            f"'{twin.twin_id}' does not provide this quantity"
        )
```

This validation also runs at contest creation time, preventing invalid combinations from being published.

---

# Extending the Ontology

New physical quantities can be added to `PhysicalQuantity` in `epic_core/quantities.py` without any other changes to the Core. Twin and sensor implementations may then declare support for the new quantity.

Adding a quantity does not require modifying existing twins or sensors. A twin that does not model a quantity simply returns `None` for it.
