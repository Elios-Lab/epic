"""Participant invitation endpoints.

POST /contests/{id}/invitations  — organizer creates invitations (bulk)
GET  /invitations/{token}         — public: validate a token
POST /invitations/{token}/accept  — public: complete registration via token
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_core.api.dependencies import (
    get_notification_service,
    get_settings,
    require_organizer_or_admin,
)
from epic_core.api.schemas import (
    AcceptInvitationResponse,
    CreateInvitationsResponse,
    InvitationDetails,
    InvitationListResponse,
)
from epic_core.api.utils import parse_uuid
from epic_core.kernel.auth import create_access_token, hash_password
from epic_core.kernel.config import Settings
from epic_core.kernel.db.models import (
    Contest,
    ContestRegistration,
    Invitation,
    User,
    USER_STATUS_ACTIVE,
)
from epic_core.kernel.db.session import get_db
from epic_core.kernel.exceptions import (
    ContestNotFoundError,
    InsufficientPermissionsError,
    SessionNotFoundError,
)
from epic_core.kernel.notifications import (
    InvitationAccepted,
    NotificationService,
    ParticipantInvitation,
)

router = APIRouter(tags=["invitations"])

_GONE_STATUS = status.HTTP_410_GONE


def _as_utc(dt: datetime) -> datetime:
    """Return dt as a timezone-aware UTC datetime.

    SQLite stores datetimes without timezone info; this helper makes comparison
    with datetime.now(timezone.utc) safe regardless of the backend.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class CreateInvitationsRequest(BaseModel):
    emails: list[str]


class AcceptInvitationRequest(BaseModel):
    first_name: str
    last_name: str
    phone_number: str | None = None
    password: str


def _invitation_summary(inv: Invitation) -> dict:
    """Public-safe invitation summary — token is intentionally omitted."""
    return {
        "id": str(inv.id),
        "email": inv.email,
        "contest_id": str(inv.contest_id),
        "expires_at": inv.expires_at,
        "used": inv.used,
        "created_at": inv.created_at,
    }


def _user_response(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at,
    }


@router.post(
    "/contests/{contest_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateInvitationsResponse,
)
async def create_invitations(
    contest_id: str,
    request: CreateInvitationsRequest,
    current_user: User = Depends(require_organizer_or_admin),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    notifications: NotificationService = Depends(get_notification_service),
):
    """Create one invitation per email address and dispatch invitation emails."""
    contest = await _owned_contest_or_raise(db, contest_id, current_user)

    created: list[Invitation] = []
    for email in request.emails:
        inv = Invitation(
            email=email,
            contest_id=contest.id,
            invited_by=current_user.id,
        )
        db.add(inv)
        created.append(inv)

    await db.commit()
    for inv in created:
        await db.refresh(inv)

    base_url = settings.base_url.rstrip("/") if hasattr(settings, "base_url") and settings.base_url else ""
    for inv in created:
        invitation_link = f"{base_url}/register?token={inv.token}"
        await notifications.notify(ParticipantInvitation(
            to_email=inv.email,
            invitation_link=invitation_link,
            contest_name=contest.name,
        ))

    return {
        "created": len(created),
        "invitations": [_invitation_summary(inv) for inv in created],
    }


async def _owned_contest_or_raise(db, contest_id: str, current_user: User) -> Contest:
    contest_uuid = parse_uuid(
        contest_id, ContestNotFoundError, f"Contest '{contest_id}' not found"
    )
    result = await db.execute(select(Contest).where(Contest.id == contest_uuid))
    contest = result.scalar_one_or_none()
    if contest is None:
        raise ContestNotFoundError(f"Contest '{contest_id}' not found")
    if current_user.role == "ORGANIZER" and contest.created_by != current_user.id:
        raise InsufficientPermissionsError(
            "Organizers can only manage invitations for their own contests"
        )
    return contest


@router.get(
    "/contests/{contest_id}/invitations", response_model=InvitationListResponse
)
async def list_contest_invitations(
    contest_id: str,
    current_user: User = Depends(require_organizer_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """List every invitation sent for a contest (owner or administrator only)."""
    contest = await _owned_contest_or_raise(db, contest_id, current_user)
    result = await db.execute(
        select(Invitation)
        .where(Invitation.contest_id == contest.id)
        .order_by(Invitation.created_at.asc())
    )
    return {
        "invitations": [_invitation_summary(inv) for inv in result.scalars()]
    }


@router.delete(
    "/contests/{contest_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invitation(
    contest_id: str,
    invitation_id: str,
    current_user: User = Depends(require_organizer_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an invitation (owner or administrator only).

    Revoking an unused invitation kills its registration link and removes the
    invitee's access to a private contest. If the invitee already joined,
    their existing registration is untouched — remove the *registration* to
    exclude them from participating.
    """
    contest = await _owned_contest_or_raise(db, contest_id, current_user)
    invitation_uuid = parse_uuid(
        invitation_id, SessionNotFoundError, "Invitation not found"
    )
    result = await db.execute(
        select(Invitation).where(
            Invitation.id == invitation_uuid,
            Invitation.contest_id == contest.id,
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise SessionNotFoundError("Invitation not found")

    await db.delete(invitation)
    await db.commit()
    from fastapi import Response
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/invitations/{token}", response_model=InvitationDetails)
async def get_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Validate an invitation token and return its public details."""
    result = await db.execute(select(Invitation).where(Invitation.token == token))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise SessionNotFoundError(f"Invitation token not found")

    contest_result = await db.execute(select(Contest).where(Contest.id == inv.contest_id))
    contest = contest_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    valid = not inv.used and _as_utc(inv.expires_at) > now

    return {
        "email": inv.email,
        "contest_id": str(inv.contest_id),
        "contest_name": contest.name if contest else None,
        "expires_at": inv.expires_at,
        "valid": valid,
    }


@router.post(
    "/invitations/{token}/accept",
    status_code=status.HTTP_201_CREATED,
    response_model=AcceptInvitationResponse,
)
async def accept_invitation(
    token: str,
    request: AcceptInvitationRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    notifications: NotificationService = Depends(get_notification_service),
):
    """Complete participant registration via a valid, unused, non-expired token."""
    result = await db.execute(select(Invitation).where(Invitation.token == token))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise SessionNotFoundError("Invitation token not found")

    now = datetime.now(timezone.utc)
    if inv.used or _as_utc(inv.expires_at) <= now:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=_GONE_STATUS,
            detail={"error": {"code": "INVITATION_GONE", "message": "Invitation has expired or was already used"}},
        )

    # Create the participant account; use email as username
    new_user = User(
        username=inv.email,
        email=inv.email,
        password_hash=hash_password(request.password),
        role="PARTICIPANT",
        status=USER_STATUS_ACTIVE,
        first_name=request.first_name,
        last_name=request.last_name,
        phone_number=request.phone_number,
    )
    db.add(new_user)
    await db.flush()

    inv.used = True
    inv.used_at = now
    inv.user_id = new_user.id

    # Link the new participant to the inviting contest immediately, as the
    # registration docs promise: no further steps before streaming/submitting.
    db.add(ContestRegistration(
        contest_id=inv.contest_id,
        user_id=new_user.id,
        status="REGISTERED",
    ))

    await db.commit()
    await db.refresh(new_user)
    await db.refresh(inv)

    # Tell the inviter their invitation was accepted.
    inviter_result = await db.execute(select(User).where(User.id == inv.invited_by))
    inviter = inviter_result.scalar_one_or_none()
    contest_result = await db.execute(select(Contest).where(Contest.id == inv.contest_id))
    contest = contest_result.scalar_one_or_none()
    if inviter is not None:
        await notifications.notify(InvitationAccepted(
            to_email=inviter.email,
            contest_name=contest.name if contest else "an EPIC contest",
            participant_email=new_user.email,
        ))

    access_token = create_access_token(
        {"sub": str(new_user.id), "username": new_user.username, "role": new_user.role},
        settings,
    )

    return {
        "user": _user_response(new_user),
        "access_token": access_token,
        "token_type": "bearer",
    }
