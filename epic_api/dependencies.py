"""FastAPI dependencies for EPIC API."""

from uuid import UUID

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from epic_core.auth import decode_access_token
from epic_core.config import Settings, get_settings as core_get_settings
from epic_core.db.models import User
from epic_core.db.session import get_db
from epic_core.exceptions import InsufficientPermissionsError, InvalidCredentialsError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_settings() -> Settings:
    return core_get_settings()


def get_engine(connection: HTTPConnection):
    return connection.app.state.engine


def get_broadcaster(connection: HTTPConnection):
    return connection.app.state.broadcaster


async def get_current_user(
    token: str = Depends(oauth2_scheme),
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


async def require_organizer_or_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role not in {"ADMINISTRATOR", "ORGANIZER"}:
        raise InsufficientPermissionsError(
            "ORGANIZER or ADMINISTRATOR privileges required"
        )
    return current_user
