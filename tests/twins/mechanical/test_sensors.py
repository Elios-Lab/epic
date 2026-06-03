from epic_twins.mechanical.sensors import (
    AccelerationSensor,
    PositionSensor,
    TemperatureSensor,
    VelocitySensor,
)
from epic_twins.mechanical.twin import MechanicalState


def _state() -> MechanicalState:
    return MechanicalState(
        position=1.0,
        velocity=2.0,
        acceleration=3.0,
        temperature=4.0,
    )


def test_each_sensor_reads_correct_field():
    state = _state()

    assert PositionSensor().observe(state) == state.position
    assert VelocitySensor().observe(state) == state.velocity
    assert AccelerationSensor().observe(state) == state.acceleration
    assert TemperatureSensor().observe(state) == state.temperature


def test_sensor_properties_match_expected_values():
    expected = (
        (PositionSensor(), "position", "Position Sensor", "m"),
        (VelocitySensor(), "velocity", "Velocity Sensor", "m/s"),
        (AccelerationSensor(), "acceleration", "Acceleration Sensor", "m/s²"),
        (TemperatureSensor(), "temperature", "Temperature Sensor", "°C"),
    )

    for sensor, sensor_id, name, unit in expected:
        assert sensor.sensor_id == sensor_id
        assert sensor.name == name
        assert sensor.unit == unit


def test_sensor_metadata_contains_required_keys():
    for sensor in (
        PositionSensor(),
        VelocitySensor(),
        AccelerationSensor(),
        TemperatureSensor(),
    ):
        metadata = sensor.metadata()
        assert metadata["sensor_id"]
        assert metadata["name"]
        assert metadata["version"]
        assert metadata["description"]


def test_observe_returns_float():
    assert isinstance(PositionSensor().observe(_state()), float)


def test_noiseless_sensor_is_deterministic():
    sensor = VelocitySensor(noise_std=0.0)
    state = _state()

    observations = [sensor.observe(state) for _ in range(10)]

    assert observations == [state.velocity] * 10


def test_noisy_sensor_observations_are_not_all_identical():
    sensor = PositionSensor(noise_std=1.0)
    state = _state()

    observations = [sensor.observe(state) for _ in range(10)]

    assert len(set(observations)) > 1
