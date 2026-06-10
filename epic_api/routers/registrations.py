"""Contest registration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_api.dependencies import get_current_user, get_notification_service
from epic_api.utils import get_contest_or_raise, parse_uuid
from epic_api.schemas import RegistrationListResponse, RegistrationResponse
from epic_core.db.models import ContestRegistration, User
from epic_core.db.session import get_db
from epic_core.notifications import NotificationService, ParticipantRegistered
from epic_core.exceptions import (
    InsufficientPermissionsError,
    RegistrationError,
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


async def get_registration_or_raise(
    db: AsyncSession, registration_id: str
) -> ContestRegistration:
    registration_uuid = parse_uuid(
        registration_id,
        RegistrationError,
        f"Registration '{registration_id}' does not exist",
    )
    result = await db.execute(
        select(ContestRegistration).where(ContestRegistration.id == registration_uuid)
    )
    registration = result.scalar_one_or_none()
    if registration is None:
        raise RegistrationError(f"Registration '{registration_id}' does not exist")
    return registration


def require_registration_access(user: User, registration: ContestRegistration) -> None:
    if user.role != "ADMINISTRATOR" and registration.user_id != user.id:
        raise InsufficientPermissionsError("Registration access denied")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RegistrationResponse)
async def create_registration(
    request: CreateRegistrationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    notifications: NotificationService = Depends(get_notification_service),
):
    contest = await get_contest_or_raise(db, request.contest_id)
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

    # Notify the contest owner (self-registrations by the owner are not notified).
    if contest.created_by is not None and contest.created_by != current_user.id:
        owner_result = await db.execute(select(User).where(User.id == contest.created_by))
        owner = owner_result.scalar_one_or_none()
        if owner is not None:
            await notifications.notify(ParticipantRegistered(
                to_email=owner.email,
                contest_name=contest.name,
                participant_username=current_user.username,
            ))

    return registration_response(registration)


@router.get("", response_model=RegistrationListResponse)
async def list_registrations(
    user_id: str | None = Query(None),
    contest_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ContestRegistration)
    if current_user.role == "ADMINISTRATOR":
        if user_id is not None:
            query = query.where(
                ContestRegistration.user_id
                == parse_uuid(user_id, RegistrationError, f"User '{user_id}' does not exist")
            )
        if contest_id is not None:
            contest = await get_contest_or_raise(db, contest_id)
            query = query.where(ContestRegistration.contest_id == contest.id)
    elif current_user.role == "ORGANIZER" and contest_id is not None:
        contest = await get_contest_or_raise(db, contest_id)
        if contest.created_by != current_user.id:
            raise InsufficientPermissionsError("Registration access denied")
        query = query.where(ContestRegistration.contest_id == contest.id)
    else:
        query = query.where(ContestRegistration.user_id == current_user.id)

    result = await db.execute(query)
    return {
        "registrations": [
            registration_response(registration) for registration in result.scalars()
        ]
    }


@router.get("/{registration_id}", response_model=RegistrationResponse)
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
