import pytest

from epic.core.quantities import PhysicalQuantity
from epic.core.testing import MockState
from epic.sensors.acceleration import AccelerationSensor
from epic.sensors.co2_concentration import CO2ConcentrationSensor
from epic.sensors.current import CurrentSensor
from epic.sensors.flow_rate import FlowRateSensor
from epic.sensors.humidity import HumiditySensor
from epic.sensors.occupancy import OccupancySensor
from epic.sensors.power import PowerSensor
from epic.sensors.position import PositionSensor
from epic.sensors.pressure import PressureSensor
from epic.sensors.rotational_speed import RotationalSpeedSensor
from epic.sensors.temperature import TemperatureSensor
from epic.sensors.velocity import VelocitySensor
from epic.sensors.vibration import VibrationSensor
from epic.sensors.voltage import VoltageSensor


def test_sensor_properties_and_metadata():
    sensors = [
        (PositionSensor(), "position", "m", PhysicalQuantity.LINEAR_POSITION),
        (VelocitySensor(), "velocity", "m/s", PhysicalQuantity.LINEAR_VELOCITY),
        (
            AccelerationSensor(),
            "acceleration",
            "m/s²",
            PhysicalQuantity.LINEAR_ACCELERATION,
        ),
        (TemperatureSensor(), "temperature", "°C", PhysicalQuantity.TEMPERATURE),
        (FlowRateSensor(), "flow_rate", "m³/h", PhysicalQuantity.FLOW_RATE),
        (PressureSensor(), "pressure", "bar", PhysicalQuantity.PRESSURE),
        (VibrationSensor(), "vibration", "mm/s", PhysicalQuantity.VIBRATION),
        (CurrentSensor(), "current", "A", PhysicalQuantity.CURRENT),
        (VoltageSensor(), "voltage", "V", PhysicalQuantity.VOLTAGE),
        (
            RotationalSpeedSensor(),
            "rotational_speed",
            "RPM",
            PhysicalQuantity.ROTATIONAL_SPEED,
        ),
        (
            CO2ConcentrationSensor(),
            "co2_concentration",
            "ppm",
            PhysicalQuantity.CO2_CONCENTRATION,
        ),
        (OccupancySensor(), "occupancy", "people", PhysicalQuantity.OCCUPANCY),
        (PowerSensor(), "power", "W", PhysicalQuantity.POWER),
        (HumiditySensor(), "humidity", "%RH", PhysicalQuantity.HUMIDITY),
    ]

    for sensor, sensor_id, unit, quantity in sensors:
        metadata = sensor.metadata()
        assert sensor.sensor_id == sensor_id
        assert sensor.unit == unit
        assert sensor.measured_quantity is quantity
        assert metadata["sensor_id"] == sensor_id
        assert metadata["measured_quantity"] == quantity.value
        assert metadata["name"]
        assert metadata["version"]
        assert metadata["description"]


def test_sensor_pipeline_applies_gain_bias_saturation_and_quantization():
    sensor = PositionSensor(gain=2.0, bias=1.0, min_value=0.0, max_value=5.0, quantization=0.5)

    assert sensor.observe(MockState(value=1.2), dt=0.1) == 3.5
    assert sensor.observe(MockState(value=10.0), dt=0.1) == 5.0


def test_drift_accumulates_over_steps():
    sensor = PositionSensor(drift_rate=0.1)
    state = MockState(value=0.0)
    dt = 1.0

    readings = [sensor.observe(state, dt=dt) for _ in range(5)]

    # Each step accumulates 0.1 * 1.0 more drift; readings should be strictly increasing
    for i in range(1, len(readings)):
        assert readings[i] > readings[i - 1], (
            f"drift not accumulating: readings[{i}]={readings[i]} <= readings[{i-1}]={readings[i-1]}"
        )
    # After 5 steps total drift = 0.1 * 1.0 * 5 = 0.5
    assert readings[-1] == pytest.approx(0.5, abs=1e-9)


def test_latency_buffer_delays_reading_by_correct_steps():
    sensor = PositionSensor(latency_steps=2)
    state_sequence = [MockState(value=float(v)) for v in range(10)]
    dt = 0.1

    readings = [sensor.observe(s, dt=dt) for s in state_sequence]

    # With latency_steps=2 the sensor should return the value from 2 steps ago.
    # Steps 0 and 1 return the oldest buffered value (0.0) while the buffer fills.
    assert readings[0] == pytest.approx(0.0)
    assert readings[1] == pytest.approx(0.0)
    # From step 2 onward, reading at step i should equal value at step i-2.
    for i in range(2, len(readings)):
        assert readings[i] == pytest.approx(float(i - 2)), (
            f"step {i}: expected {i - 2}, got {readings[i]}"
        )


def test_p_false_reading_replaces_measurement():
    # p_false_reading=1.0 means every reading is a wrong value
    sensor = PositionSensor(
        p_false_reading=1.0,
        min_value=-10.0,
        max_value=10.0,
    )
    state = MockState(value=0.0)

    readings = [sensor.observe(state) for _ in range(50)]

    # With p=1.0 every reading is a random uniform in [min, max]; none should be exactly 0.0
    # (the probability of hitting exactly 0.0 from a continuous uniform is zero)
    assert all(-10.0 <= r <= 10.0 for r in readings)
    # At least some readings should differ from the true value of 0.0
    assert any(r != pytest.approx(0.0) for r in readings)


def test_p_false_reading_zero_produces_true_value():
    sensor = PositionSensor(p_false_reading=0.0)
    state = MockState(value=3.0)

    readings = [sensor.observe(state) for _ in range(20)]

    assert all(r == pytest.approx(3.0) for r in readings)


def test_p_outlier_produces_spikes():
    # p_outlier=1.0 means every reading is an outlier spike.
    # noise_std=0.0 keeps the base measurement at exactly 0 so the spike
    # (±10 * (noise_std or 1.0) = ±10) is the only contribution.
    sensor = PositionSensor(p_outlier=1.0, noise_std=0.0)
    state = MockState(value=0.0)

    readings = [sensor.observe(state) for _ in range(50)]

    assert all(abs(r) == pytest.approx(10.0) for r in readings), (
        f"expected all readings to be ±10 outliers: {readings[:5]}"
    )


def test_saturation_clamps_min_and_max():
    sensor = PositionSensor(min_value=0.0, max_value=5.0)

    assert sensor.observe(MockState(value=-100.0)) == pytest.approx(0.0)
    assert sensor.observe(MockState(value=100.0)) == pytest.approx(5.0)
    assert sensor.observe(MockState(value=2.5)) == pytest.approx(2.5)


def test_quantization_rounds_to_resolution():
    sensor = PositionSensor(quantization=0.25)

    assert sensor.observe(MockState(value=1.1)) == pytest.approx(1.0)
    assert sensor.observe(MockState(value=1.15)) == pytest.approx(1.25)
    assert sensor.observe(MockState(value=1.0)) == pytest.approx(1.0)


def test_injected_rng_reproduces_sequence():
    """Two sensors seeded with identical Random instances produce identical
    noisy readings, independent of the global random module state."""
    import random

    state = MockState(value=1.0)
    sensor_a = PositionSensor(noise_std=0.5, rng=random.Random(42))
    sensor_b = PositionSensor(noise_std=0.5, rng=random.Random(42))

    random.seed(0)  # perturb global state — must not matter
    readings_a = [sensor_a.observe(state) for _ in range(10)]
    random.seed(99999)
    readings_b = [sensor_b.observe(state) for _ in range(10)]

    assert readings_a == readings_b


def test_injected_rng_isolated_from_global_random():
    """Draws on the global random module must not influence a sensor with an
    injected RNG (concurrent sessions must not interfere)."""
    import random

    state = MockState(value=1.0)
    sensor_a = PositionSensor(noise_std=0.5, rng=random.Random(7))
    readings_clean = [sensor_a.observe(state) for _ in range(5)]

    sensor_b = PositionSensor(noise_std=0.5, rng=random.Random(7))
    readings_interleaved = []
    for _ in range(5):
        random.random()  # simulate another session drawing from global RNG
        readings_interleaved.append(sensor_b.observe(state))

    assert readings_clean == readings_interleaved


def test_sensor_without_rng_uses_global_seeding():
    """Backward compatibility: without an injected RNG, global random.seed()
    still makes readings reproducible."""
    import random

    state = MockState(value=1.0)

    random.seed(123)
    readings_a = [PositionSensor(noise_std=0.5).observe(state) for _ in range(5)]
    random.seed(123)
    readings_b = [PositionSensor(noise_std=0.5).observe(state) for _ in range(5)]

    assert readings_a == readings_b
