from epic_core.quantities import PhysicalQuantity
from epic_core.testing import MockState
from epic_sensors.acceleration import AccelerationSensor
from epic_sensors.position import PositionSensor
from epic_sensors.temperature import TemperatureSensor
from epic_sensors.velocity import VelocitySensor


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
