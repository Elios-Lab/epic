from epic_core.quantities import PhysicalQuantity
from epic_core.testing import MockState
from epic_sensors.acceleration import AccelerationSensor
from epic_sensors.co2_concentration import CO2ConcentrationSensor
from epic_sensors.current import CurrentSensor
from epic_sensors.flow_rate import FlowRateSensor
from epic_sensors.occupancy import OccupancySensor
from epic_sensors.power import PowerSensor
from epic_sensors.position import PositionSensor
from epic_sensors.pressure import PressureSensor
from epic_sensors.rotational_speed import RotationalSpeedSensor
from epic_sensors.temperature import TemperatureSensor
from epic_sensors.velocity import VelocitySensor
from epic_sensors.vibration import VibrationSensor
from epic_sensors.voltage import VoltageSensor


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
