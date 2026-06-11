import pytest
from pydantic import ValidationError

from epic_core.config import Settings, get_settings


def test_settings_raise_validation_error_when_database_url_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-characters-xx")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-characters-xx")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("PORT", "9000")

    settings = Settings()

    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.secret_key == "test-secret-key-32-characters-xx"
    assert settings.debug is True
    assert settings.port == 9000
    assert settings.app_name == "EPIC"


def test_get_settings_constructs_settings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-characters-xx")
    monkeypatch.delenv("DEBUG", raising=False)

    assert get_settings().database_url == "sqlite+aiosqlite:///:memory:"


def test_debug_error_content_includes_traceback_only_for_server_errors():
    """DEBUG=true adds a traceback to 5xx envelopes; 4xx and production stay clean."""
    from epic_api.errors import error_content
    from epic_core.exceptions import ContestNotFoundError, PluginExecutionError

    try:
        raise PluginExecutionError("twin exploded")
    except PluginExecutionError as exc:
        server_error = exc

    debug_payload = error_content(server_error, debug=True)
    assert "traceback" in debug_payload["error"]
    assert any("twin exploded" in line for line in debug_payload["error"]["traceback"])

    prod_payload = error_content(server_error, debug=False)
    assert "traceback" not in prod_payload["error"]

    client_error = ContestNotFoundError("nope")
    debug_4xx = error_content(client_error, debug=True)
    assert "traceback" not in debug_4xx["error"]
