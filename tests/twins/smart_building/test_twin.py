import pytest

import epic_core.registry as registry_module
from epic_core.interfaces import FaultDescriptor, SimulationState
from epic_core.quantities import PhysicalQuantity
from epic_core.testing import test_registry_context as registry_context
from epic_twins.smart_building.plugin import register
from epic_twins.smart_building.twin import SmartBuildingState, SmartBuildingTwin


def _schedule(fault_id: str, severity: float = 1.0, end_time=None) -> list[dict]:
    return [
        {
            "fault_id": fault_id,
            "start_time": 0.0,
            "end_time": end_time,
            "severity": severity,
        }
    ]


def test_configure_returns_valid_state():
    state = SmartBuildingTwin().configure(
        {"temperature": 23.0, "humidity": 48.0, "co2": 700.0, "occupancy": 30},
        [],
    )

    assert isinstance(state, SimulationState)
    assert isinstance(state, SmartBuildingState)
    assert state.temperature == pytest.approx(23.0)
    assert state.humidity == pytest.approx(48.0)
    assert state.co2 == pytest.approx(700.0)
    assert state.occupancy == 30
    assert state.time == 0.0
    assert state.get_quantity(PhysicalQuantity.TEMPERATURE) == pytest.approx(23.0)
    assert state.get_quantity(PhysicalQuantity.HUMIDITY) == pytest.approx(48.0)
    assert state.get_quantity(PhysicalQuantity.CO2_CONCENTRATION) == pytest.approx(
        700.0
    )
    assert state.get_quantity(PhysicalQuantity.OCCUPANCY) == pytest.approx(30.0)


def test_step_advances_time():
    twin = SmartBuildingTwin()
    state = twin.configure(None, [])

    new_state = twin.step(state, 0.1)

    assert new_state is not state
    assert new_state.time == pytest.approx(0.1)


def test_get_active_faults_reflects_schedule():
    twin = SmartBuildingTwin()
    state = twin.configure(None, _schedule("hvac_failure", severity=0.7))

    twin.step(state, 0.1)

    assert twin.get_active_faults() == [{"fault_id": "hvac_failure", "severity": 0.7}]


def test_fault_deactivates_after_end_time():
    twin = SmartBuildingTwin()
    state = twin.configure(None, _schedule("hvac_failure", severity=0.7, end_time=0.05))

    twin.step(state, 0.1)

    assert twin.get_active_faults() == []


def test_hvac_failure_reduces_power_and_raises_co2():
    baseline_twin = SmartBuildingTwin()
    faulted_twin = SmartBuildingTwin()
    initial_conditions = {"temperature": 26.0, "co2": 700.0}
    baseline_state = baseline_twin.configure(initial_conditions, [])
    faulted_state = faulted_twin.configure(
        initial_conditions, _schedule("hvac_failure")
    )

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.hvac_power < baseline_next.hvac_power
    assert faulted_next.co2 > baseline_next.co2


def test_sensor_drift_changes_temperature_and_humidity():
    baseline_twin = SmartBuildingTwin()
    faulted_twin = SmartBuildingTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("sensor_drift"))

    for _ in range(10):
        baseline_state = baseline_twin.step(baseline_state, 0.1)
        faulted_state = faulted_twin.step(faulted_state, 0.1)

    assert faulted_state.temperature > baseline_state.temperature
    assert faulted_state.humidity > baseline_state.humidity


def test_occupancy_spike_raises_occupancy_co2_and_humidity():
    baseline_twin = SmartBuildingTwin()
    faulted_twin = SmartBuildingTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("occupancy_spike"))

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.occupancy > baseline_next.occupancy
    assert faulted_next.co2 > baseline_next.co2
    assert faulted_next.humidity > baseline_next.humidity


def test_metadata_supported_quantities_faults_and_plugin_registration():
    twin = SmartBuildingTwin()

    assert twin.metadata()["twin_id"] == "smart_building"
    assert {
        PhysicalQuantity.TEMPERATURE,
        PhysicalQuantity.HUMIDITY,
        PhysicalQuantity.CO2_CONCENTRATION,
        PhysicalQuantity.OCCUPANCY,
    } == twin.supported_quantities()
    assert all(isinstance(fault, FaultDescriptor) for fault in twin.get_faults())
    assert {fault.fault_id for fault in twin.get_faults()} == {
        "hvac_failure",
        "sensor_drift",
        "occupancy_spike",
    }

    with registry_context():
        register()
        assert registry_module.twin_registry.contains("smart_building")
