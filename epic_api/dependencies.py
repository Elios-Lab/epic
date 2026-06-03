"""FastAPI dependencies for EPIC API."""

from epic_core.config import Settings, get_settings as core_get_settings


def get_settings() -> Settings:
    return core_get_settings()

