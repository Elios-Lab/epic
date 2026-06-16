import pytest

import epic_core.kernel.registry as registry_module
from epic_core.api.errors import error_to_code, error_to_status_code
from epic_core.kernel.exceptions import (
    ContestNotFoundError,
    ContestStateError,
    EPICError,
    EPICValidationError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    PluginExecutionError,
    PluginNotFoundError,
    PluginValidationError,
    RegistrationError,
    SessionNotFoundError,
    SessionStateError,
    SubmissionError,
)
from epic_core.kernel.testing import test_registry_context as registry_context
from epic_plugins.sensors.plugin import register as register_sensors
from epic_plugins.twins.mass_spring_damper.plugin import register


def test_list_twins_returns_registered_twin_metadata(client):
    response = client.get("/api/v1/twins")

    assert response.status_code == 200
    body = response.json()
    assert "twins" in body
    assert any(twin["twin_id"] == "mass_spring_damper" for twin in body["twins"])


def test_get_twin_returns_metadata(client):
    response = client.get("/api/v1/twins/mass_spring_damper")

    assert response.status_code == 200
    body = response.json()
    assert body["twin_id"] == "mass_spring_damper"
    assert body["name"]
    assert body["version"]
    assert body["description"]


def test_get_nonexistent_twin_returns_standard_404_error(client):
    response = client.get("/api/v1/twins/nonexistent")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "PLUGIN_NOT_FOUND"
    assert body["error"]["message"]


def test_list_twin_sensors_returns_sensor_metadata(client):
    response = client.get("/api/v1/twins/mass_spring_damper/sensors")

    assert response.status_code == 200
    body = response.json()
    assert body["twin_id"] == "mass_spring_damper"
    assert body["sensors"]
    assert all("sensor_id" in sensor for sensor in body["sensors"])


def test_list_twin_faults_returns_fault_metadata(client):
    response = client.get("/api/v1/twins/mass_spring_damper/faults")

    assert response.status_code == 200
    body = response.json()
    assert body["twin_id"] == "mass_spring_damper"
    assert body["faults"]
    assert all("fault_id" in fault for fault in body["faults"])


@pytest.mark.parametrize(
    ("exception", "expected_status_code", "expected_error_code"),
    [
        (PluginNotFoundError("missing plugin"), 404, "PLUGIN_NOT_FOUND"),
        (SessionNotFoundError("missing session"), 404, "SESSION_NOT_FOUND"),
        (ContestNotFoundError("missing contest"), 404, "CONTEST_NOT_FOUND"),
        (ContestStateError("bad contest state"), 409, "CONTEST_STATE_ERROR"),
        (SessionStateError("bad session state"), 409, "SESSION_STATE_ERROR"),
        (RegistrationError("registration failed"), 409, "REGISTRATION_ERROR"),
        (SubmissionError("submission failed"), 422, "SUBMISSION_ERROR"),
        (EPICValidationError("invalid request"), 422, "VALIDATION_ERROR"),
        (InvalidCredentialsError("invalid credentials"), 401, "INVALID_CREDENTIALS"),
        (InsufficientPermissionsError("forbidden"), 403, "FORBIDDEN"),
        (
            PluginValidationError("plugin validation failed"),
            500,
            "PLUGIN_VALIDATION_ERROR",
        ),
        (PluginExecutionError("plugin execution failed"), 500, "PLUGIN_EXECUTION_ERROR"),
    ],
)
def test_error_mapping_table(exception, expected_status_code, expected_error_code):
    assert error_to_status_code(exception) == expected_status_code
    assert error_to_code(exception) == expected_error_code


def test_unknown_epic_error_maps_to_internal_error():
    class UnknownEPICError(EPICError):
        pass

    exception = UnknownEPICError("unknown")

    assert error_to_status_code(exception) == 500
    assert error_to_code(exception) == "INTERNAL_ERROR"


def test_mass_spring_damper_register_populates_twin_registry():
    with registry_context():
        register_sensors()
        register()

        assert registry_module.twin_registry.contains("mass_spring_damper")
        assert registry_module.sensor_registry.contains("position")
