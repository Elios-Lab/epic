"""Administrator environment-file management endpoints."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError

from epic_core.api.dependencies import require_admin
from epic_core.kernel.config import Settings
from epic_core.kernel.db.models import User
from epic_core.kernel.exceptions import EPICValidationError

router = APIRouter(prefix="/admin/environment", tags=["admin"])


@dataclass(frozen=True)
class EnvVarDefinition:
    key: str
    field: str
    category: str
    description: str
    required: bool = False
    secret: bool = False


ENV_DEFINITIONS = [
    EnvVarDefinition("APP_NAME", "app_name", "Application", "Application display name."),
    EnvVarDefinition("APP_VERSION", "app_version", "Application", "Application version string."),
    EnvVarDefinition("DEBUG", "debug", "Application", "Enable debug logging and debug error details."),
    EnvVarDefinition("HOST", "host", "Server", "Host address used by local server commands."),
    EnvVarDefinition("PORT", "port", "Server", "Port used by local server commands."),
    EnvVarDefinition("DATABASE_URL", "database_url", "Database", "SQLAlchemy database URL.", required=True, secret=True),
    EnvVarDefinition("SECRET_KEY", "secret_key", "Authentication", "JWT signing secret.", required=True, secret=True),
    EnvVarDefinition("ALGORITHM", "algorithm", "Authentication", "JWT signing algorithm."),
    EnvVarDefinition("ACCESS_TOKEN_EXPIRE_MINUTES", "access_token_expire_minutes", "Authentication", "Access token lifetime in minutes."),
    EnvVarDefinition("ADMIN_USERNAME", "admin_username", "Bootstrap Admin", "Bootstrap administrator username."),
    EnvVarDefinition("ADMIN_EMAIL", "admin_email", "Bootstrap Admin", "Bootstrap administrator email."),
    EnvVarDefinition("ADMIN_PASSWORD", "admin_password", "Bootstrap Admin", "Bootstrap administrator password.", secret=True),
    EnvVarDefinition("MAX_CONCURRENT_SESSIONS", "max_concurrent_sessions", "Simulation", "Maximum active simulation runners in this API process."),
    EnvVarDefinition("DEFAULT_SAMPLING_RATE_HZ", "default_sampling_rate_hz", "Simulation", "Default sampling rate for generated sessions."),
    EnvVarDefinition("SESSION_QUEUE_CAPACITY", "session_queue_capacity", "Simulation", "Per-client WebSocket queue capacity."),
    EnvVarDefinition("BASE_URL", "base_url", "Notifications", "Public base URL used in invitation links."),
    EnvVarDefinition("SMTP_HOST", "smtp_host", "SMTP", "SMTP host. Leave empty to disable email delivery."),
    EnvVarDefinition("SMTP_PORT", "smtp_port", "SMTP", "SMTP port."),
    EnvVarDefinition("SMTP_USERNAME", "smtp_username", "SMTP", "SMTP username."),
    EnvVarDefinition("SMTP_PASSWORD", "smtp_password", "SMTP", "SMTP password.", secret=True),
    EnvVarDefinition("SMTP_SENDER", "smtp_sender", "SMTP", "SMTP sender address. Defaults to admin email when empty."),
    EnvVarDefinition("SMTP_TLS", "smtp_tls", "SMTP", "Use STARTTLS for SMTP delivery."),
]

DEFINITIONS_BY_KEY = {definition.key: definition for definition in ENV_DEFINITIONS}
ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


class EnvVarResponse(BaseModel):
    key: str
    category: str
    description: str
    value: str | None
    is_secret: bool
    is_required: bool
    is_set: bool
    requires_restart: bool = True


class EnvironmentResponse(BaseModel):
    env_file: str
    variables: list[EnvVarResponse]


class EnvironmentUpdateRequest(BaseModel):
    values: dict[str, str | None]


def env_file_path(request: Request) -> Path:
    configured = getattr(request.app.state, "env_file_path", None)
    if configured is not None:
        return Path(configured)
    return Path(".env").resolve()


def parse_env_assignments(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ASSIGNMENT_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        raw_value = line.split("=", 1)[1].strip()
        values[key] = unquote_env_value(raw_value)
    return values


def unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.replace("\\n", "\n")


def quote_env_value(value: str) -> str:
    if value == "":
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./:@%+,\-]+", value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def current_value(settings: Settings, env_values: dict[str, str], definition: EnvVarDefinition) -> str | None:
    if definition.key in env_values:
        return env_values[definition.key]
    value = getattr(settings, definition.field)
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def environment_response(path: Path, settings: Settings) -> EnvironmentResponse:
    env_values = parse_env_assignments(path)
    variables = []
    for definition in ENV_DEFINITIONS:
        value = current_value(settings, env_values, definition)
        variables.append(EnvVarResponse(
            key=definition.key,
            category=definition.category,
            description=definition.description,
            value=None if definition.secret else value,
            is_secret=definition.secret,
            is_required=definition.required,
            is_set=value not in (None, ""),
        ))
    return EnvironmentResponse(env_file=str(path), variables=variables)


def write_env_file(path: Path, values: dict[str, str | None]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept_lines = []
    for line in existing_lines:
        match = ASSIGNMENT_RE.match(line)
        if match and match.group(1) in DEFINITIONS_BY_KEY:
            continue
        kept_lines.append(line)

    managed_lines = ["# EPIC settings managed from the administrator UI"]
    for definition in ENV_DEFINITIONS:
        value = values.get(definition.key)
        if value in (None, ""):
            continue
        managed_lines.append(f"{definition.key}={quote_env_value(value)}")

    content_lines = [line for line in kept_lines if line.strip()]
    if content_lines:
        content_lines.append("")
    content_lines.extend(managed_lines)
    content = "\n".join(content_lines) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def validate_settings_values(values: dict[str, str | None]) -> None:
    data = {
        definition.field: values.get(definition.key)
        for definition in ENV_DEFINITIONS
        if values.get(definition.key) not in (None, "")
    }
    try:
        Settings(**data)
    except ValidationError as exc:
        raise EPICValidationError(str(exc)) from exc


@router.get("", response_model=EnvironmentResponse)
async def get_environment(
    request: Request,
    current_user: User = Depends(require_admin),
):
    del current_user
    return environment_response(env_file_path(request), request.app.state.settings)


@router.put("", response_model=EnvironmentResponse)
async def update_environment(
    payload: EnvironmentUpdateRequest,
    request: Request,
    current_user: User = Depends(require_admin),
):
    del current_user
    unknown = sorted(set(payload.values) - set(DEFINITIONS_BY_KEY))
    if unknown:
        raise EPICValidationError(f"Unknown environment variable(s): {', '.join(unknown)}")

    path = env_file_path(request)
    existing = parse_env_assignments(path)
    merged: dict[str, str | None] = {}
    settings = request.app.state.settings
    for definition in ENV_DEFINITIONS:
        merged[definition.key] = current_value(settings, existing, definition)

    for key, value in payload.values.items():
        merged[key] = value.strip() if isinstance(value, str) else None

    missing_required = [
        definition.key
        for definition in ENV_DEFINITIONS
        if definition.required and not merged.get(definition.key)
    ]
    if missing_required:
        raise EPICValidationError(
            f"Required environment variable(s) cannot be empty: {', '.join(missing_required)}"
        )

    validate_settings_values(merged)
    write_env_file(path, merged)
    return environment_response(path, settings)
