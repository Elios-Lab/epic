# Configuration

> Related: [Architecture](architecture.md) · [Authentication](authentication.md)

EPIC is configured through environment variables.

The configuration system is implemented using [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/), which reads values from environment variables and an optional `.env` file, validates them at startup, and exposes a single typed `Settings` object to the rest of the application.

---

# Settings Location

```text
epic_core/
└── config.py    ← Settings class and get_settings() function
```

---

# Settings Class

```python
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
    database_url: str  # required — no default

    # Authentication
    secret_key: str    # required — no default
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Simulation
    max_concurrent_sessions: int = 50
    default_sampling_rate_hz: float = 10.0
    session_queue_capacity: int = 1000

    # Plugin Discovery
    plugin_discovery: str = "explicit"
    # "explicit" = plugins registered in startup code
    # "entrypoints" = auto-discovery via Python entry points


def get_settings() -> Settings:
    return Settings()
```

The `Settings` object is instantiated once and cached using FastAPI's dependency injection:

```python
from functools import lru_cache
from epic_core.config import Settings

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

All components that need configuration receive it via dependency injection rather than importing `get_settings()` directly.

---

# Required Variables

The following variables have no defaults and must be set before the application will start:

| Variable | Description |
|---|---|
| `DATABASE_URL` | SQLAlchemy-compatible database URL |
| `SECRET_KEY` | Secret key for JWT signing (min 32 characters) |

If either is missing, Pydantic raises a `ValidationError` at startup with a clear message.

---

# All Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `EPIC` | Application name used in API responses |
| `APP_VERSION` | `0.1.0` | Application version |
| `DEBUG` | `false` | Enable debug mode (verbose logging, reload) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DATABASE_URL` | — | Database connection string |
| `SECRET_KEY` | — | JWT signing secret |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT access token lifetime |
| `MAX_CONCURRENT_SESSIONS` | `50` | Maximum concurrent simulation sessions (one per active contest) |
| `DEFAULT_SAMPLING_RATE_HZ` | `10.0` | Default sensor sampling rate for new contests |
| `SESSION_QUEUE_CAPACITY` | `1000` | Max buffered observations per WebSocket client |
| `PLUGIN_DISCOVERY` | `explicit` | Plugin discovery mode (`explicit` or `entrypoints`) |

---

## Admin Bootstrap

To create the first administrator account automatically on startup,
set the following environment variables:

| Variable         | Required | Description                                      |
|------------------|----------|--------------------------------------------------|
| `ADMIN_USERNAME` | No       | Username of the bootstrap administrator account  |
| `ADMIN_EMAIL`    | No       | Email address (defaults to `username@epic.local`)|
| `ADMIN_PASSWORD` | No       | Password for the bootstrap account               |

If `ADMIN_USERNAME` is set but the account already exists and is already
an administrator, startup continues without making any changes.

If `ADMIN_USERNAME` is set and the account exists with a different role,
the account is promoted to ADMINISTRATOR.

If `ADMIN_USERNAME` is not set, the bootstrap step is skipped entirely.

Example `.env` entry:

```
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@elioslab.it
ADMIN_PASSWORD=change-me-in-production
```

The bootstrap step is idempotent: if the account already exists with the ADMINISTRATOR role, startup continues without changes. It is therefore safe to leave these variables set across restarts. Remove them only if you want to prevent automatic role promotion of an existing account on the next restart.

---

# Environment File

Create a `.env` file in the project root for local development:

```dotenv
DATABASE_URL=postgresql+asyncpg://epic:epic@localhost:5432/epic
SECRET_KEY=change-me-to-a-random-32-char-string
DEBUG=true
```

The `.env` file must never be committed to version control. Add it to `.gitignore`.

For production, set variables directly in the environment or via a secrets manager.

---

# Database URL Examples

| Database | URL format |
|---|---|
| PostgreSQL (async) | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| SQLite (development) | `sqlite+aiosqlite:///./epic.db` |

PostgreSQL with `asyncpg` is the recommended production database. SQLite with `aiosqlite` is acceptable for local development and testing.

---

# Validation

Pydantic validates all values at startup.

If a required variable is missing or a value fails type validation, the application raises a `ValidationError` and refuses to start. This is intentional — a misconfigured application should not start silently.

Example error:

```text
pydantic_core.ValidationError: 1 validation error for Settings
database_url
  Field required [type=missing, input_url=<URL>, input_type=dict]
```

---

# Adding New Configuration Keys

To add a new configuration key, add the field to the `Settings` class in `epic_core/config.py`, document it in the table above, and give it a default value unless the key is genuinely required — required keys without defaults make local development needlessly painful.

Plugin packages must not define their own `Settings` subclasses. If a plugin needs configuration, it should read from the main `Settings` object using a namespaced prefix (e.g. `MECHANICAL_TWIN_MASS=1.5`), declared as an optional field with a default.
