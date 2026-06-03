import inspect

import pytest

from epic_core.interfaces import (
    DigitalTwin,
    Fault,
    OperatingProfile,
    Scenario,
    ScoringMetric,
    Sensor,
    SensorFault,
    SimulationState,
)
from epic_core.testing import (
    MockFault,
    MockScenario,
    MockSensor,
    MockSensorFault,
    MockState,
    MockTwin,
)


def test_interfaces_are_abstract():
    for interface in (
        DigitalTwin,
        Sensor,
        Fault,
        SensorFault,
        Scenario,
        OperatingProfile,
        ScoringMetric,
    ):
        assert inspect.isabstract(interface)


def test_mock_twin_implements_digital_twin():
    twin = MockTwin()

    state = twin.create_initial_state({"value": 2.0})
    new_state = twin.step(state, 0.5)

    assert isinstance(state, SimulationState)
    assert new_state is not state
    assert getattr(new_state, "value") == 2.5
    assert isinstance(twin.get_sensors()[0], Sensor)
    assert isinstance(twin.get_faults()[0], Fault)
    assert isinstance(twin.get_scenarios()[0], Scenario)
    assert twin.metadata()["twin_id"] == twin.twin_id


def test_mock_sensor_observes_constant_value():
    sensor = MockSensor(sensor_id="sensor_a", constant_value=7.0)

    assert sensor.sensor_id == "sensor_a"
    assert sensor.name
    assert sensor.unit
    assert sensor.observe(object()) == 7.0
    assert sensor.metadata()["sensor_id"] == "sensor_a"


def test_mock_fault_tracks_activation_and_apply_count():
    fault = MockFault()

    assert fault.current_severity == 0.0
    fault.activate(0.25)
    fault.apply(MockState(), 1.0)
    fault.deactivate()

    assert fault.apply_count == 1
    assert fault.current_severity == 0.0
    assert fault.metadata()["fault_id"] == fault.fault_id


def test_mock_sensor_fault_corrupts_measurement():
    fault = MockSensorFault(target_sensor_ids=["mock_sensor"])

    fault.activate(0.5)

    assert isinstance(fault, SensorFault)
    assert fault.target_sensor_ids == ["mock_sensor"]
    assert fault.apply_to_measurement(1.0) == 1.5


def test_mock_scenario_returns_initialization_and_schedule():
    schedule = [
        {
            "fault_id": "mock_fault",
            "start_time": 10.0,
            "end_time": None,
            "severity": 1.0,
        }
    ]
    scenario = MockScenario(scenario_id="scenario_a", fault_schedule=schedule)

    assert scenario.scenario_id == "scenario_a"
    assert scenario.name
    assert scenario.initialize()["initial_conditions"]["value"] == 0.0
    assert scenario.get_fault_schedule() == schedule
    assert scenario.metadata()["scenario_id"] == "scenario_a"


def test_incomplete_abstract_sensor_cannot_be_instantiated():
    class IncompleteSensor(Sensor):
        @property
        def sensor_id(self) -> str:
            return "incomplete"

        @property
        def name(self) -> str:
            return "Incomplete"

        @property
        def unit(self) -> str:
            return "unit"

        def metadata(self) -> dict:
            return {}

    with pytest.raises(TypeError):
        IncompleteSensor()
