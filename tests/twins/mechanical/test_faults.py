from epic_core.interfaces import SensorFault
from epic_twins.mechanical.faults import (
    IncreasedDampingFault,
    ReducedStiffnessFault,
    SensorBiasFault,
)
from epic_twins.mechanical.twin import MechanicalState


def _state() -> MechanicalState:
    return MechanicalState(
        position=0.1,
        velocity=1.0,
        acceleration=0.0,
        temperature=20.0,
        mass=1.0,
        stiffness=10.0,
        damping=0.5,
    )


def test_increased_damping_fault_increases_damping_after_apply():
    fault = IncreasedDampingFault()
    state = _state()

    fault.activate(1.0)
    fault.apply(state, 1.0)

    assert state.damping > 0.5


def test_reduced_stiffness_fault_decreases_stiffness_after_apply():
    fault = ReducedStiffnessFault()
    state = _state()

    fault.activate(1.0)
    fault.apply(state, 1.0)

    assert state.stiffness < 10.0


def test_reduced_stiffness_fault_never_drops_below_one():
    fault = ReducedStiffnessFault()
    state = _state()

    fault.activate(1.0)
    fault.apply(state, 1000.0)

    assert state.stiffness == 1.0


def test_sensor_bias_fault_measurement_depends_on_severity():
    fault = SensorBiasFault()

    assert fault.apply_to_measurement(1.0) == 1.0

    fault.activate(0.8)

    assert fault.apply_to_measurement(1.0) > 1.0


def test_sensor_bias_fault_is_sensor_fault_subclass():
    assert isinstance(SensorBiasFault(), SensorFault)


def test_sensor_bias_fault_id():
    assert SensorBiasFault().fault_id == "sensor_bias"


def test_sensor_bias_fault_default_targets_all_sensors():
    assert SensorBiasFault().target_sensor_ids == []


def test_sensor_bias_fault_deactivate_resets_severity():
    fault = SensorBiasFault()

    fault.activate(0.8)
    fault.deactivate()

    assert fault.current_severity == 0.0


def test_sensor_bias_fault_metadata_contains_required_keys():
    metadata = SensorBiasFault().metadata()

    assert metadata["fault_id"]
    assert metadata["name"]
    assert metadata["version"]
    assert metadata["description"]


def test_current_severity_is_zero_before_activate():
    assert IncreasedDampingFault().current_severity == 0.0


def test_current_severity_resets_after_deactivate():
    fault = ReducedStiffnessFault()

    fault.activate(0.8)
    fault.deactivate()

    assert fault.current_severity == 0.0


def test_increased_damping_severity_grows_over_repeated_apply_calls():
    fault = IncreasedDampingFault()
    state = _state()

    fault.activate(0.1)
    initial_severity = fault.current_severity
    for _ in range(5):
        fault.apply(state, 1.0)

    assert fault.current_severity > initial_severity
