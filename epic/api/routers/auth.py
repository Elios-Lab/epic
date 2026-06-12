"""Authentication endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic.api.dependencies import get_current_user, get_settings
from epic.api.schemas import MeResponse, TokenResponse
from epic.core.auth import create_access_token, verify_password
from epic.core.config import Settings
from epic.core.db.models import User
from epic.core.db.session import get_db
from epic.core.exceptions import InvalidCredentialsError

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    result = await db.execute(select(User).where(User.username == request.username))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(request.password, user.password_hash)
    ):
        raise InvalidCredentialsError("Invalid credentials")

    token = create_access_token(
        {"sub": str(user.id), "username": user.username, "role": user.role},
        settings,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)):
    return {
        "user_id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
    }

