import pytest

import epic_core.registry as registry_module
from epic_core.interfaces import FaultDescriptor, SimulationState
from epic_core.quantities import PhysicalQuantity
from epic_core.testing import test_registry_context as registry_context
from epic_twins.electric_motor.plugin import register
from epic_twins.electric_motor.twin import ElectricMotorState, ElectricMotorTwin


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
    state = ElectricMotorTwin().configure(
        {"current": 14.0, "voltage": 415.0, "speed": 1500.0}, []
    )

    assert isinstance(state, SimulationState)
    assert isinstance(state, ElectricMotorState)
    assert state.current == pytest.approx(14.0)
    assert state.voltage == pytest.approx(415.0)
    assert state.speed == pytest.approx(1500.0)
    assert state.time == 0.0
    assert state.get_quantity(PhysicalQuantity.CURRENT) == pytest.approx(14.0)
    assert state.get_quantity(PhysicalQuantity.VOLTAGE) == pytest.approx(415.0)
    assert state.get_quantity(PhysicalQuantity.ROTATIONAL_SPEED) == pytest.approx(
        1500.0
    )
    assert state.get_quantity(PhysicalQuantity.TEMPERATURE) == pytest.approx(
        state.temperature
    )


def test_step_advances_time():
    twin = ElectricMotorTwin()
    state = twin.configure(None, [])

    new_state = twin.step(state, 0.1)

    assert new_state is not state
    assert new_state.time == pytest.approx(0.1)


def test_get_active_faults_reflects_schedule():
    twin = ElectricMotorTwin()
    state = twin.configure(None, _schedule("overheating", severity=0.6))

    twin.step(state, 0.1)

    assert twin.get_active_faults() == [{"fault_id": "overheating", "severity": 0.6}]


def test_fault_deactivates_after_end_time():
    twin = ElectricMotorTwin()
    state = twin.configure(None, _schedule("overheating", severity=0.6, end_time=0.05))

    twin.step(state, 0.1)

    assert twin.get_active_faults() == []


def test_overheating_raises_temperature_and_degrades_hot_motor_output():
    baseline_twin = ElectricMotorTwin()
    faulted_twin = ElectricMotorTwin()
    baseline_state = baseline_twin.configure({"temperature": 90.0}, [])
    faulted_state = faulted_twin.configure(
        {"temperature": 90.0}, _schedule("overheating")
    )

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.temperature > baseline_next.temperature
    assert faulted_next.speed < baseline_next.speed
    assert faulted_next.torque < baseline_next.torque


def test_bearing_fault_changes_speed_and_raises_temperature():
    baseline_twin = ElectricMotorTwin()
    faulted_twin = ElectricMotorTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("bearing_fault"))

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.speed != pytest.approx(baseline_next.speed)
    assert faulted_next.temperature > baseline_next.temperature


def test_voltage_imbalance_raises_current_temperature_and_reduces_torque():
    baseline_twin = ElectricMotorTwin()
    faulted_twin = ElectricMotorTwin()
    baseline_state = baseline_twin.configure(None, [])
    faulted_state = faulted_twin.configure(None, _schedule("voltage_imbalance"))

    baseline_next = baseline_twin.step(baseline_state, 0.1)
    faulted_next = faulted_twin.step(faulted_state, 0.1)

    assert faulted_next.current > baseline_next.current
    assert faulted_next.temperature > baseline_next.temperature
    assert faulted_next.torque < baseline_next.torque


def test_metadata_supported_quantities_faults_and_plugin_registration():
    twin = ElectricMotorTwin()

    assert twin.metadata()["twin_id"] == "electric_motor"
    assert {
        PhysicalQuantity.CURRENT,
        PhysicalQuantity.VOLTAGE,
        PhysicalQuantity.ROTATIONAL_SPEED,
        PhysicalQuantity.TEMPERATURE,
        PhysicalQuantity.TORQUE,
    } == twin.supported_quantities()
    assert all(isinstance(fault, FaultDescriptor) for fault in twin.get_faults())
    assert {fault.fault_id for fault in twin.get_faults()} == {
        "overheating",
        "bearing_fault",
        "voltage_imbalance",
    }

    with registry_context():
        register()
        assert registry_module.twin_registry.contains("electric_motor")
