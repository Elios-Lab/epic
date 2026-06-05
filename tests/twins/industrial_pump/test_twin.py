import pytest

import epic_core.registry as registry_module
from epic_core.interfaces import FaultDescriptor, SimulationState
from epic_core.quantities import PhysicalQuantity
from epic_core.testing import test_registry_context as registry_context
from epic_twins.industrial_pump.plugin import register
from epic_twins.industrial_pump.twin import IndustrialPumpState, IndustrialPumpTwin


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
    state = IndustrialPumpTwin().configure({"flow_rate": 130.0, "wear": 0.2}, [])

    assert isinstance(state, SimulationState)
    assert isinstance(state, IndustrialPumpState)
    assert state.flow_rate == pytest.approx(130.0)
    assert state.wear == pytest.approx(0.2)
    assert state.time == 0.0
    assert state.get_quantity(PhysicalQuantity.FLOW_RATE) == pytest.approx(130.0)
    assert state.get_quantity(PhysicalQuantity.PRESSURE) == pytest.approx(state.pressure)
    assert state.get_quantity(PhysicalQuantity.TEMPERATURE) == pytest.approx(
        state.temperature
    )
    assert state.get_quantity(PhysicalQuantity.VIBRATION) == pytest.approx(
        state.vibration
    )


def test_step_advances_time():
    twin = IndustrialPumpTwin()
    state = twin.configure(None, [])

    new_state = twin.step(state, 0.5)

    assert new_state is not state
    assert new_state.time == pytest.approx(0.5)


def test_initial_flow_and_pressure_influence_trajectory():
    default_twin = IndustrialPumpTwin()
    configured_twin = IndustrialPumpTwin()
    default_state = default_twin.configure(None, [])
    configured_state = configured_twin.configure(
        {"flow_rate": 150.0, "pressure": 6.0}, []
    )

    default_next = default_twin.step(default_state, 0.1)
    configured_next = configured_twin.step(configured_state, 0.1)

    assert configured_next.flow_rate > default_next.flow_rate
    assert configured_next.pressure > default_next.pressure


def test_get_active_faults_reflects_schedule():
    twin = IndustrialPumpTwin()
    state = twin.configure(None, _schedule("cavitation", severity=0.4))

    twin.step(state, 0.1)

    assert twin.get_active_faults() == [{"fault_id": "cavitation", "severity": 0.4}]


def test_fault_deactivates_after_end_time():
    twin = IndustrialPumpTwin()
    state = twin.configure(None, _schedule("cavitation", severity=0.4, end_time=0.05))

    twin.step(state, 0.1)

    assert twin.get_active_faults() == []


def test_cavitation_reduces_flow_and_raises_vibration():
    baseline_twin = IndustrialPumpTwin()
    faulted_twin = IndustrialPumpTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("cavitation"))

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.flow_rate < baseline_next.flow_rate
    assert faulted_next.vibration > baseline_next.vibration


def test_bearing_wear_increases_wear_vibration_and_temperature():
    baseline_twin = IndustrialPumpTwin()
    faulted_twin = IndustrialPumpTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("bearing_wear"))

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.wear > baseline_next.wear
    assert faulted_next.vibration > baseline_next.vibration
    assert faulted_next.temperature > baseline_next.temperature


def test_filter_clog_reduces_flow_and_increases_pressure():
    baseline_twin = IndustrialPumpTwin()
    faulted_twin = IndustrialPumpTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("filter_clog"))

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.flow_rate < baseline_next.flow_rate
    assert faulted_next.pressure > baseline_next.pressure


def test_metadata_supported_quantities_faults_and_plugin_registration():
    twin = IndustrialPumpTwin()

    assert twin.metadata()["twin_id"] == "industrial_pump"
    assert {
        PhysicalQuantity.FLOW_RATE,
        PhysicalQuantity.PRESSURE,
        PhysicalQuantity.TEMPERATURE,
        PhysicalQuantity.VIBRATION,
    } == twin.supported_quantities()
    assert all(isinstance(fault, FaultDescriptor) for fault in twin.get_faults())
    assert {fault.fault_id for fault in twin.get_faults()} == {
        "cavitation",
        "bearing_wear",
        "filter_clog",
    }

    with registry_context():
        register()
        assert registry_module.twin_registry.contains("industrial_pump")
