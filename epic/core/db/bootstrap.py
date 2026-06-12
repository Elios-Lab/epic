"""Admin bootstrap — seeds the first administrator account on startup."""

from __future__ import annotations

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic.core.config import Settings
from epic.core.db.models import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed_admin(settings: Settings, db: AsyncSession) -> None:
    """Create or promote the bootstrap admin user if credentials are configured.

    - If ADMIN_USERNAME is not set, do nothing.
    - If the user already exists and is ADMINISTRATOR, do nothing.
    - If the user already exists but has a different role, promote to ADMINISTRATOR.
    - If the user does not exist, create it as ADMINISTRATOR.

    This function is idempotent: safe to call on every startup.
    """
    if not settings.admin_username:
        return

    result = await db.execute(
        select(User).where(User.username == settings.admin_username)
    )
    user = result.scalar_one_or_none()

    if user is None:
        if not settings.admin_password:
            raise RuntimeError(
                "ADMIN_USERNAME is set but ADMIN_PASSWORD is missing. "
                "Cannot create bootstrap admin."
            )
        email = settings.admin_email or f"{settings.admin_username}@epic.local"
        db.add(
            User(
                username=settings.admin_username,
                email=email,
                password_hash=_pwd_context.hash(settings.admin_password),
                role="ADMINISTRATOR",
            )
        )
        await db.commit()
    elif user.role != "ADMINISTRATOR":
        user.role = "ADMINISTRATOR"
        await db.commit()
