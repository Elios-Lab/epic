"""User registration endpoints."""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_api.dependencies import require_admin
from epic_api.utils import parse_uuid
from epic_core.auth import hash_password
from epic_core.db.models import User
from epic_core.db.session import get_db
from epic_core.exceptions import EPICValidationError, RegistrationError, SessionNotFoundError

router = APIRouter(prefix="/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


ALLOWED_ROLES = {"ADMINISTRATOR", "ORGANIZER", "PARTICIPANT"}


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


@router.get("")
async def list_users(
    role: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    count_query = select(func.count()).select_from(User)
    if role is not None:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    total_result = await db.execute(count_query)
    result = await db.execute(query.offset(offset).limit(limit))
    return {
        "total": total_result.scalar_one(),
        "users": [user_response(user) for user in result.scalars()],
    }


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user_uuid = parse_uuid(
        user_id,
        SessionNotFoundError,
        f"User '{user_id}' does not exist",
    )
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        raise SessionNotFoundError(f"User '{user_id}' does not exist")
    return user_response(user)


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user_uuid = parse_uuid(
        user_id,
        SessionNotFoundError,
        f"User '{user_id}' does not exist",
    )
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        raise SessionNotFoundError(f"User '{user_id}' does not exist")
    if request.role is not None:
        if request.role not in ALLOWED_ROLES:
            raise EPICValidationError(f"role '{request.role}' is not supported")
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active
    await db.commit()
    await db.refresh(user)
    return user_response(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user_uuid = parse_uuid(
        user_id,
        SessionNotFoundError,
        f"User '{user_id}' does not exist",
    )
    if user_uuid == current_user.id:
        raise EPICValidationError("Cannot deactivate self")
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        raise SessionNotFoundError(f"User '{user_id}' does not exist")
    user.is_active = False
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
