from epic_core.interfaces import FaultDescriptor
from epic_core.quantities import PhysicalQuantity
from epic_twins.mass_spring_damper.faults import (
    IncreasedDampingFault,
    IncreasedFrictionFault,
    ReducedStiffnessFault,
)
from epic_twins.mass_spring_damper.twin import MassSpringDamperState


def _state() -> MassSpringDamperState:
    return MassSpringDamperState(
        position=0.1,
        velocity=1.0,
        acceleration=0.0,
        temperature=20.0,
        mass=1.0,
        stiffness=10.0,
        damping=0.5,
        time=0.0,
    )


def test_faults_implement_fault_descriptor():
    for fault in (IncreasedDampingFault(), ReducedStiffnessFault(), IncreasedFrictionFault()):
        assert isinstance(fault, FaultDescriptor)


def test_faults_have_required_metadata():
    for fault in (IncreasedDampingFault(), ReducedStiffnessFault(), IncreasedFrictionFault()):
        metadata = fault.metadata()
        assert metadata["fault_id"]
        assert metadata["name"]
        assert metadata["version"]
        assert metadata["description"]


def test_increased_damping_raises_damping():
    state = _state()
    IncreasedDampingFault().apply(state, severity=1.0, dt=1.0)

    assert state.damping > 0.5


def test_reduced_stiffness_lowers_stiffness():
    state = _state()
    ReducedStiffnessFault().apply(state, severity=1.0, dt=1.0)

    assert state.stiffness < 10.0


def test_increased_friction_raises_temperature_and_damping():
    state = _state()
    IncreasedFrictionFault().apply(state, severity=1.0, dt=1.0)

    assert state.temperature > 20.0
    assert state.damping > 0.5
    assert state.get_quantity(PhysicalQuantity.TEMPERATURE) == state.temperature


def test_zero_severity_has_no_effect():
    state = _state()
    IncreasedDampingFault().apply(state, severity=0.0, dt=1.0)

    assert state.damping == 0.5
