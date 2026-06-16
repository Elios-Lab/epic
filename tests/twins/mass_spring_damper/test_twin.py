import pytest

import epic_core.kernel.registry as registry_module
from epic_core.kernel.interfaces import FaultDescriptor, SimulationState
from epic_core.kernel.quantities import PhysicalQuantity
from epic_core.kernel.testing import MockState, test_registry_context as registry_context
from epic_plugins.twins.mass_spring_damper.plugin import register
from epic_plugins.twins.mass_spring_damper.twin import MassSpringDamperState, MassSpringDamperTwin


def test_configure_returns_state_with_initial_conditions():
    state = MassSpringDamperTwin().configure({"position": 0.2}, [])

    assert isinstance(state, SimulationState)
    assert isinstance(state, MassSpringDamperState)
    assert state.position == pytest.approx(0.2)
    assert state.time == 0.0
    assert state.get_quantity(PhysicalQuantity.LINEAR_POSITION) == pytest.approx(0.2)


def test_configure_uses_defaults_when_no_initial_conditions():
    state = MassSpringDamperTwin().configure(None, [])

    assert isinstance(state, MassSpringDamperState)
    assert state.position == pytest.approx(0.1)


def test_step_returns_new_state_and_advances_time():
    twin = MassSpringDamperTwin()
    state = twin.configure(None, [])

    new_state = twin.step(state, 0.1)

    assert new_state is not state
    assert new_state.time == pytest.approx(0.1)


def test_step_rejects_non_mass_spring_damper_state():
    twin = MassSpringDamperTwin()
    twin.configure(None, [])

    with pytest.raises(TypeError):
        twin.step(MockState(), 0.1)


def test_get_active_faults_empty_before_schedule_start():
    twin = MassSpringDamperTwin()
    schedule = [
        {
            "fault_id": "increased_damping",
            "start_time": 100.0,
            "end_time": None,
            "severity": 0.5,
        }
    ]
    state = twin.configure(None, schedule)
    twin.step(state, 0.1)

    assert twin.get_active_faults() == []


def test_fault_activates_at_scheduled_time():
    twin = MassSpringDamperTwin()
    schedule = [
        {
            "fault_id": "increased_damping",
            "start_time": 0.0,
            "end_time": None,
            "severity": 0.3,
        }
    ]
    state = twin.configure(None, schedule)
    twin.step(state, 0.1)

    active = twin.get_active_faults()

    assert len(active) == 1
    assert active[0]["fault_id"] == "increased_damping"
    assert active[0]["severity"] == pytest.approx(0.3)


def test_fault_deactivates_after_end_time():
    twin = MassSpringDamperTwin()
    schedule = [
        {
            "fault_id": "increased_damping",
            "start_time": 0.0,
            "end_time": 0.05,
            "severity": 0.5,
        }
    ]
    state = twin.configure(None, schedule)
    twin.step(state, 0.1)

    assert twin.get_active_faults() == []


def test_fault_alters_damping_during_step():
    twin = MassSpringDamperTwin()
    no_fault_twin = MassSpringDamperTwin()
    schedule = [
        {
            "fault_id": "increased_damping",
            "start_time": 0.0,
            "end_time": None,
            "severity": 1.0,
        }
    ]
    state_no_fault = no_fault_twin.configure(None, [])
    state_with_fault = twin.configure(None, schedule)

    for _ in range(10):
        state_no_fault = no_fault_twin.step(state_no_fault, 0.1)
        state_with_fault = twin.step(state_with_fault, 0.1)

    assert state_with_fault.damping > state_no_fault.damping


def test_twin_metadata_supported_quantities_and_faults():
    twin = MassSpringDamperTwin()

    assert twin.metadata()["twin_id"] == "mass_spring_damper"
    assert PhysicalQuantity.LINEAR_POSITION in twin.supported_quantities()
    assert PhysicalQuantity.TEMPERATURE in twin.supported_quantities()
    assert all(isinstance(fault, FaultDescriptor) for fault in twin.get_faults())
    fault_ids = {fault.fault_id for fault in twin.get_faults()}
    assert "increased_damping" in fault_ids
    assert "reduced_stiffness" in fault_ids
    assert "increased_friction" in fault_ids


def test_plugin_registers_mass_spring_damper_twin():
    with registry_context():
        register()

        assert registry_module.twin_registry.contains("mass_spring_damper")
