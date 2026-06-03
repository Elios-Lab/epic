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
