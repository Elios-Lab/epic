import inspect

import pytest

from epic_core.interfaces import (
    DigitalTwin,
    FaultDescriptor,
    ScoringMetric,
    Sensor,
    SimulationState,
)
from epic_core.quantities import PhysicalQuantity
from epic_core.testing import MockFaultDescriptor, MockSensor, MockState, MockTwin


def test_interfaces_are_abstract():
    for interface in (DigitalTwin, Sensor, FaultDescriptor, ScoringMetric):
        assert inspect.isabstract(interface)


def test_mock_state_returns_supported_quantity():
    state = MockState(value=2.0)

    assert state.get_quantity(PhysicalQuantity.LINEAR_POSITION) == 2.0
    assert state.get_quantity(PhysicalQuantity.TEMPERATURE) is None


def test_mock_twin_configure_returns_state():
    twin = MockTwin()

    state = twin.configure({"value": 2.0}, [])

    assert isinstance(state, SimulationState)
    assert state.get_quantity(PhysicalQuantity.LINEAR_POSITION) == 2.0


def test_mock_twin_step_advances_value():
    twin = MockTwin()
    state = twin.configure(None, [])

    new_state = twin.step(state, 0.5)

    assert new_state is not state
    assert new_state.get_quantity(PhysicalQuantity.LINEAR_POSITION) == pytest.approx(
        0.5
    )


def test_mock_twin_get_active_faults_empty_with_no_schedule():
    twin = MockTwin()
    twin.configure(None, [])

    assert twin.get_active_faults() == []


def test_mock_twin_get_active_faults_after_schedule_activates():
    twin = MockTwin()
    schedule = [
        {
            "fault_id": "mock_fault",
            "start_time": 0.0,
            "end_time": None,
            "severity": 0.5,
        }
    ]
    twin.configure(None, schedule)
    twin.step(MockState(), 0.1)

    active = twin.get_active_faults()

    assert len(active) == 1
    assert active[0]["fault_id"] == "mock_fault"
    assert active[0]["severity"] == 0.5


def test_mock_twin_reports_no_active_faults_before_start_time():
    twin = MockTwin()
    schedule = [
        {
            "fault_id": "mock_fault",
            "start_time": 100.0,
            "end_time": None,
            "severity": 0.5,
        }
    ]
    twin.configure(None, schedule)
    twin.step(MockState(), 0.1)

    assert twin.get_active_faults() == []


def test_mock_twin_metadata_and_supported_quantities():
    twin = MockTwin()

    assert twin.metadata()["twin_id"] == twin.twin_id
    assert PhysicalQuantity.LINEAR_POSITION in twin.supported_quantities()
    assert isinstance(twin.get_faults()[0], FaultDescriptor)


def test_mock_sensor_observes_constant_value():
    sensor = MockSensor(sensor_id="sensor_a", constant_value=7.0)

    assert sensor.sensor_id == "sensor_a"
    assert sensor.name
    assert sensor.unit
    assert sensor.measured_quantity is PhysicalQuantity.LINEAR_POSITION
    assert sensor.observe(MockState(), dt=0.1) == 7.0
    assert sensor.metadata()["sensor_id"] == "sensor_a"


def test_mock_fault_descriptor_has_required_metadata():
    fault = MockFaultDescriptor()

    assert fault.fault_id
    assert fault.name
    assert "fault_id" in fault.metadata()
    assert "name" in fault.metadata()
    assert "description" in fault.metadata()


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

        @property
        def measured_quantity(self) -> PhysicalQuantity:
            return PhysicalQuantity.LINEAR_POSITION

        def metadata(self) -> dict:
            return {}

    with pytest.raises(TypeError):
        IncompleteSensor()
