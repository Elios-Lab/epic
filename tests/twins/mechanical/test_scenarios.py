from epic_twins.mechanical.scenarios import (
    IncreasedDampingScenario,
    NormalOperationScenario,
    SensorBiasScenario,
)


def test_normal_operation_scenario_has_empty_fault_schedule():
    assert NormalOperationScenario().get_fault_schedule() == []


def test_increased_damping_scenario_fault_schedule():
    assert IncreasedDampingScenario().get_fault_schedule() == [
        {
            "fault_id": "increased_damping",
            "start_time": 30.0,
            "end_time": None,
            "severity": 0.1,
        }
    ]


def test_sensor_bias_scenario_fault_schedule():
    assert SensorBiasScenario().get_fault_schedule() == [
        {
            "fault_id": "sensor_bias",
            "start_time": 20.0,
            "end_time": None,
            "severity": 0.8,
        }
    ]


def test_all_scenarios_have_valid_metadata():
    for scenario in (
        NormalOperationScenario(),
        IncreasedDampingScenario(),
        SensorBiasScenario(),
    ):
        metadata = scenario.metadata()
        assert metadata["scenario_id"]
        assert metadata["name"]
        assert metadata["version"]
        assert metadata["description"]

