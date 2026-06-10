"""Configuration settings for EPIC Core."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    ) 

    # Application
    app_name: str = "EPIC"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str

    # Authentication
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    admin_username: str | None = None
    admin_email: str | None = None
    admin_password: str | None = None

    # Simulation
    max_concurrent_sessions: int = 50
    default_sampling_rate_hz: float = 10.0
    session_queue_capacity: int = 1000

    # Base URL used to build invitation links in notification emails
    base_url: str = "http://localhost:8000"

    # SMTP — all optional; if smtp_host is unset, notifications are no-ops
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_sender: str | None = None   # falls back to admin_email if unset
    smtp_tls: bool = True            # STARTTLS (port 587); set False for plain/SSL port 465

    # Plugin Discovery
    plugin_discovery: str = "explicit"


@lru_cache
def get_settings() -> Settings:
    return Settings()
