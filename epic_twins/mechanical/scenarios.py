"""Scenarios for the mechanical twin."""

from __future__ import annotations

from epic_core.interfaces import Scenario


class _BaseScenario(Scenario):
    scenario_id_value: str
    name_value: str
    description_value: str

    def __init__(self, version: str = "1.0.0") -> None:
        self._version = version

    @property
    def scenario_id(self) -> str:
        return self.scenario_id_value

    @property
    def name(self) -> str:
        return self.name_value

    def initialize(self) -> dict:
        return {}

    def metadata(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "version": self._version,
            "description": self.description_value,
        }


class NormalOperationScenario(_BaseScenario):
    scenario_id_value = "normal_operation"
    name_value = "Normal Operation"
    description_value = "Nominal mechanical system operation"

    def get_fault_schedule(self) -> list[dict]:
        return []


class IncreasedDampingScenario(_BaseScenario):
    scenario_id_value = "increased_damping"
    name_value = "Increased Damping"
    description_value = "Scenario with increased damping fault"

    def get_fault_schedule(self) -> list[dict]:
        return [
            {
                "fault_id": "increased_damping",
                "start_time": 30.0,
                "end_time": None,
                "severity": 0.1,
            }
        ]


class SensorBiasScenario(_BaseScenario):
    scenario_id_value = "sensor_bias"
    name_value = "Sensor Bias"
    description_value = "Scenario with sensor bias fault"

    def get_fault_schedule(self) -> list[dict]:
        return [
            {
                "fault_id": "sensor_bias",
                "start_time": 20.0,
                "end_time": None,
                "severity": 0.8,
            }
        ]

