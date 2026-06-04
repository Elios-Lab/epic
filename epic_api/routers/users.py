"""User registration endpoints."""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_core.auth import hash_password
from epic_core.db.models import User
from epic_core.db.session import get_db
from epic_core.exceptions import RegistrationError

router = APIRouter(prefix="/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str


def user_response(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(
            or_(User.username == request.username, User.email == request.email)
        )
    )
    existing_user = result.scalar_one_or_none()
    if existing_user is not None:
        if existing_user.username == request.username:
            raise RegistrationError(f"Username '{request.username}' already exists")
        raise RegistrationError(f"Email '{request.email}' already exists")

    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user_response(user)

