import math

import pytest

import epic_core.registry as registry_module
from epic_core.interfaces import Fault, Scenario, Sensor
from epic_core.testing import test_registry_context as registry_context
from epic_twins.mechanical.plugin import register
from epic_twins.mechanical.twin import MechanicalState, MechanicalTwin


def test_create_initial_state_returns_mechanical_state():
    twin = MechanicalTwin()

    state = twin.create_initial_state()

    assert isinstance(state, MechanicalState)


def test_create_initial_state_applies_override():
    twin = MechanicalTwin()

    state = twin.create_initial_state({"position": 0.5})

    assert state.position == 0.5


def test_step_returns_new_state_without_modifying_input_state():
    twin = MechanicalTwin()
    state = twin.create_initial_state()
    before = MechanicalState(**state.__dict__)

    new_state = twin.step(state, 0.01)

    assert isinstance(new_state, MechanicalState)
    assert new_state is not state
    assert state == before


def test_step_rejects_non_mechanical_state():
    twin = MechanicalTwin()

    with pytest.raises(TypeError):
        twin.step(object(), 0.01)


def test_state_remains_finite_after_100_steps():
    twin = MechanicalTwin()
    state = twin.create_initial_state()

    for _ in range(100):
        state = twin.step(state, 0.01)

    assert math.isfinite(state.position)
    assert math.isfinite(state.velocity)


def test_twin_metadata_and_components_match_contract_expectations():
    twin = MechanicalTwin()
    metadata = twin.metadata()

    assert metadata["twin_id"] == "mechanical_system"
    assert metadata["name"]
    assert metadata["version"] == "1.0.0"
    assert metadata["description"]
    assert all(isinstance(sensor, Sensor) for sensor in twin.get_sensors())
    assert all(isinstance(fault, Fault) for fault in twin.get_faults())
    assert all(isinstance(scenario, Scenario) for scenario in twin.get_scenarios())


def test_plugin_registers_mechanical_plugins():
    with registry_context():
        register()

        assert registry_module.twin_registry.contains("mechanical_system")
        assert registry_module.sensor_registry.contains("position")
        assert registry_module.sensor_registry.contains("velocity")
        assert registry_module.sensor_registry.contains("acceleration")
        assert registry_module.sensor_registry.contains("temperature")
        assert registry_module.fault_registry.contains("increased_damping")
        assert registry_module.fault_registry.contains("reduced_stiffness")
        assert registry_module.fault_registry.contains("sensor_bias")
