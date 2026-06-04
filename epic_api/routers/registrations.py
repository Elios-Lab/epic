"""Contest registration endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_api.dependencies import get_current_user
from epic_core.db.models import Contest, ContestRegistration, User
from epic_core.db.session import get_db
from epic_core.exceptions import (
    ContestNotFoundError,
    InsufficientPermissionsError,
    RegistrationError,
    SessionNotFoundError,
)

router = APIRouter(prefix="/contest-registrations", tags=["contest-registrations"])


class CreateRegistrationRequest(BaseModel):
    contest_id: str


def registration_response(registration: ContestRegistration) -> dict:
    return {
        "registration_id": str(registration.id),
        "contest_id": str(registration.contest_id),
        "user_id": str(registration.user_id),
        "registered_at": registration.registered_at.isoformat(),
        "status": registration.status,
    }


def parse_uuid(value: str, error_cls, message: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise error_cls(message) from exc


async def get_registration_or_raise(
    db: AsyncSession, registration_id: str
) -> ContestRegistration:
    registration_uuid = parse_uuid(
        registration_id,
        SessionNotFoundError,
        f"Registration '{registration_id}' does not exist",
    )
    result = await db.execute(
        select(ContestRegistration).where(ContestRegistration.id == registration_uuid)
    )
    registration = result.scalar_one_or_none()
    if registration is None:
        raise SessionNotFoundError(f"Registration '{registration_id}' does not exist")
    return registration


def require_registration_access(user: User, registration: ContestRegistration) -> None:
    if user.role != "ADMINISTRATOR" and registration.user_id != user.id:
        raise InsufficientPermissionsError("Registration access denied")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_registration(
    request: CreateRegistrationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contest_uuid = parse_uuid(
        request.contest_id,
        ContestNotFoundError,
        f"Contest '{request.contest_id}' does not exist",
    )
    contest_result = await db.execute(select(Contest).where(Contest.id == contest_uuid))
    contest = contest_result.scalar_one_or_none()
    if contest is None:
        raise ContestNotFoundError(f"Contest '{request.contest_id}' does not exist")
    if contest.status not in {"SCHEDULED", "ACTIVE"}:
        raise RegistrationError("Contest is not open for registration")

    existing_result = await db.execute(
        select(ContestRegistration).where(
            ContestRegistration.user_id == current_user.id,
            ContestRegistration.contest_id == contest.id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise RegistrationError("Already registered for this contest")

    registration = ContestRegistration(
        contest_id=contest.id,
        user_id=current_user.id,
        status="REGISTERED",
    )
    db.add(registration)
    await db.commit()
    await db.refresh(registration)
    return registration_response(registration)


@router.get("")
async def list_registrations(
    user_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ContestRegistration)
    if current_user.role == "ADMINISTRATOR":
        if user_id is not None:
            query = query.where(
                ContestRegistration.user_id
                == parse_uuid(user_id, SessionNotFoundError, f"User '{user_id}' does not exist")
            )
    else:
        query = query.where(ContestRegistration.user_id == current_user.id)

    result = await db.execute(query)
    return {
        "registrations": [
            registration_response(registration) for registration in result.scalars()
        ]
    }


@router.get("/{registration_id}")
async def get_registration(
    registration_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    registration = await get_registration_or_raise(db, registration_id)
    require_registration_access(current_user, registration)
    return registration_response(registration)


@router.delete("/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_registration(
    registration_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    registration = await get_registration_or_raise(db, registration_id)
    require_registration_access(current_user, registration)
    if registration.status != "REGISTERED":
        raise RegistrationError("Registration cannot be withdrawn")

    registration.status = "WITHDRAWN"
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
