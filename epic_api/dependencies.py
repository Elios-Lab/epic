"""FastAPI dependencies for EPIC API."""

from uuid import UUID

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection, Request

from epic_core.auth import decode_access_token
from epic_core.config import Settings, get_settings as core_get_settings
from epic_core.db.models import User
from epic_core.db.session import get_db
from epic_core.exceptions import InsufficientPermissionsError, InvalidCredentialsError
from epic_core.notifications import NotificationService, NullNotificationService
# imported lazily inside get_notification_service to avoid a circular import
# and to keep epic_core free of delivery-layer imports

# Kept only for OpenAPI / Swagger UI — the lock icon and token input box.
# Not used in the actual auth logic.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_settings() -> Settings:
    return core_get_settings()


def get_engine(connection: HTTPConnection):
    return connection.app.state.engine


def get_broadcaster(connection: HTTPConnection):
    return connection.app.state.broadcaster


async def _extract_bearer_token(request: Request) -> str:
    """
    Read the Bearer token from the Authorization header and raise
    InvalidCredentialsError (→ our standard 401 envelope) if it is
    absent or malformed.  This replaces OAuth2PasswordBearer as the
    actual token source so that every 401 path produces the same
    {"error": {"code": "INVALID_CREDENTIALS", …}} response.
    """
    authorization = request.headers.get("Authorization", "")
    scheme, token = get_authorization_scheme_param(authorization)
    if not authorization or scheme.lower() != "bearer" or not token:
        raise InvalidCredentialsError(
            "Missing or malformed Authorization header — expected 'Bearer <token>'"
        )
    return token


async def get_current_user(
    token: str = Depends(_extract_bearer_token),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    payload = decode_access_token(token, settings)
    subject = payload.get("sub")
    if subject is None:
        raise InvalidCredentialsError("Invalid access token")

    try:
        user_id = UUID(subject)
    except ValueError as exc:
        raise InvalidCredentialsError("Invalid access token") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise InvalidCredentialsError("Invalid credentials")
    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "ADMINISTRATOR":
        raise InsufficientPermissionsError("Administrator privileges required")
    return current_user


def get_notification_service(
    settings: Settings = Depends(get_settings),
) -> NotificationService:
    """Auto-select the NotificationService based on configuration.

    - smtp_host set  → EmailNotificationService (production)
    - smtp_host unset → NullNotificationService (no-op)

    Override this dependency in tests with a CollectingNotificationService.
    """
    if settings.smtp_host:
        from epic_api.email_service import EmailNotificationService
        return EmailNotificationService(settings)
    return NullNotificationService()


async def require_organizer_or_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role not in {"ADMINISTRATOR", "ORGANIZER"}:
        raise InsufficientPermissionsError(
            "ORGANIZER or ADMINISTRATOR privileges required"
        )
    return current_user
