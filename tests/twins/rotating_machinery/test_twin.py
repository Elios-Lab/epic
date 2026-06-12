import pytest

import epic.core.registry as registry_module
from epic.core.interfaces import FaultDescriptor, SimulationState
from epic.core.quantities import PhysicalQuantity
from epic.core.testing import test_registry_context as registry_context
from epic.twins.rotating_machinery.plugin import register
from epic.twins.rotating_machinery.twin import (
    RotatingMachineryState,
    RotatingMachineryTwin,
)


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
    state = RotatingMachineryTwin().configure(
        {"speed": 1750.0, "vibration": 1.5, "power": 80000.0}, []
    )

    assert isinstance(state, SimulationState)
    assert isinstance(state, RotatingMachineryState)
    assert state.speed == pytest.approx(1750.0)
    assert state.vibration == pytest.approx(1.5)
    assert state.power == pytest.approx(80000.0)
    assert state.time == 0.0
    assert state.get_quantity(PhysicalQuantity.ROTATIONAL_SPEED) == pytest.approx(
        1750.0
    )
    assert state.get_quantity(PhysicalQuantity.VIBRATION) == pytest.approx(1.5)
    assert state.get_quantity(PhysicalQuantity.TEMPERATURE) == pytest.approx(
        state.temperature
    )
    assert state.get_quantity(PhysicalQuantity.POWER) == pytest.approx(80000.0)


def test_step_advances_time():
    twin = RotatingMachineryTwin()
    state = twin.configure(None, [])

    new_state = twin.step(state, 0.1)

    assert new_state is not state
    assert new_state.time == pytest.approx(0.1)


def test_get_active_faults_reflects_schedule():
    twin = RotatingMachineryTwin()
    state = twin.configure(None, _schedule("unbalance", severity=0.8))

    twin.step(state, 0.1)

    assert twin.get_active_faults() == [{"fault_id": "unbalance", "severity": 0.8}]


def test_fault_deactivates_after_end_time():
    twin = RotatingMachineryTwin()
    state = twin.configure(None, _schedule("unbalance", severity=0.8, end_time=0.05))

    twin.step(state, 0.1)

    assert twin.get_active_faults() == []


def test_unbalance_raises_vibration_and_deflection():
    baseline_twin = RotatingMachineryTwin()
    faulted_twin = RotatingMachineryTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("unbalance"))

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.vibration > baseline_next.vibration
    assert faulted_next.shaft_deflection > baseline_next.shaft_deflection


def test_misalignment_raises_vibration_temperature_and_power():
    baseline_twin = RotatingMachineryTwin()
    faulted_twin = RotatingMachineryTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("misalignment"))

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.vibration > baseline_next.vibration
    assert faulted_next.temperature > baseline_next.temperature
    assert faulted_next.power > baseline_next.power


def test_gear_tooth_wear_raises_vibration_temperature_and_deflection():
    baseline_twin = RotatingMachineryTwin()
    faulted_twin = RotatingMachineryTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("gear_tooth_wear"))

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.vibration > baseline_next.vibration
    assert faulted_next.temperature > baseline_next.temperature
    assert faulted_next.shaft_deflection > baseline_next.shaft_deflection


def test_metadata_supported_quantities_faults_and_plugin_registration():
    twin = RotatingMachineryTwin()

    assert twin.metadata()["twin_id"] == "rotating_machinery"
    assert {
        PhysicalQuantity.ROTATIONAL_SPEED,
        PhysicalQuantity.VIBRATION,
        PhysicalQuantity.TEMPERATURE,
        PhysicalQuantity.POWER,
    } == twin.supported_quantities()
    assert all(isinstance(fault, FaultDescriptor) for fault in twin.get_faults())
    assert {fault.fault_id for fault in twin.get_faults()} == {
        "unbalance",
        "misalignment",
        "gear_tooth_wear",
    }

    with registry_context():
        register()
        assert registry_module.twin_registry.contains("rotating_machinery")
