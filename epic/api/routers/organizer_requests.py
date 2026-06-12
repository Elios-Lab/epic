"""Organizer self-registration and admin approval endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from epic.api.dependencies import get_notification_service, get_settings, require_admin
from epic.api.utils import parse_uuid
from epic.api.schemas import OrganizerRequestListResponse, OrganizerRequestResponse
from epic.core.auth import hash_password
from epic.core.config import Settings
from epic.core.db.models import (
    OrganizerRequest,
    User,
    ORGANIZER_REQUEST_APPROVED,
    ORGANIZER_REQUEST_PENDING,
    ORGANIZER_REQUEST_REJECTED,
    USER_STATUS_ACTIVE,
)
from epic.core.db.session import get_db
from epic.core.exceptions import RegistrationError, SessionNotFoundError
from epic.core.notifications import (
    NotificationService,
    OrganizerApproved,
    OrganizerRejected,
    OrganizerRequestReceived,
)

router = APIRouter(prefix="/organizer-requests", tags=["organizer-requests"])


class OrganizerRegistrationRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone_number: str | None = None
    password: str


def _request_response(req: OrganizerRequest) -> dict:
    return {
        "id": str(req.id),
        "first_name": req.first_name,
        "last_name": req.last_name,
        "email": req.email,
        "phone_number": req.phone_number,
        "status": req.status,
        "reviewed_at": req.reviewed_at,
        "user_id": str(req.user_id) if req.user_id else None,
        "created_at": req.created_at,
    }


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OrganizerRequestResponse)
async def register_organizer(
    request: OrganizerRegistrationRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    notifications: NotificationService = Depends(get_notification_service),
):
    """Public endpoint: submit an organizer registration request.

    The account is NOT created immediately — it enters a PENDING queue
    for administrator review.
    """
    existing = await db.execute(
        select(OrganizerRequest).where(OrganizerRequest.email == request.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise RegistrationError(f"Email '{request.email}' already has a pending or decided request")

    # Also reject if there is already an active user with this email
    existing_user = await db.execute(select(User).where(User.email == request.email))
    if existing_user.scalar_one_or_none() is not None:
        raise RegistrationError(f"Email '{request.email}' is already registered")

    org_request = OrganizerRequest(
        first_name=request.first_name,
        last_name=request.last_name,
        email=request.email,
        phone_number=request.phone_number,
        password_hash=hash_password(request.password),
    )
    db.add(org_request)
    await db.commit()
    await db.refresh(org_request)

    admin_email = settings.admin_email or f"{settings.admin_username}@epic.local"
    await notifications.notify(OrganizerRequestReceived(
        to_email=admin_email,
        request_id=str(org_request.id),
        requester_email=org_request.email,
    ))

    return _request_response(org_request)


@router.get("", response_model=OrganizerRequestListResponse)
async def list_organizer_requests(
    request_status: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(OrganizerRequest)
    count_query = select(func.count()).select_from(OrganizerRequest)
    if request_status is not None:
        query = query.where(OrganizerRequest.status == request_status)
        count_query = count_query.where(OrganizerRequest.status == request_status)

    total_result = await db.execute(count_query)
    result = await db.execute(query.offset(offset).limit(limit))
    return {
        "total": total_result.scalar_one(),
        "requests": [_request_response(r) for r in result.scalars()],
    }


@router.post("/{request_id}/approve", response_model=OrganizerRequestResponse)
async def approve_organizer_request(
    request_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    notifications: NotificationService = Depends(get_notification_service),
):
    req_uuid = parse_uuid(request_id, SessionNotFoundError, f"Request '{request_id}' not found")
    result = await db.execute(select(OrganizerRequest).where(OrganizerRequest.id == req_uuid))
    org_request = result.scalar_one_or_none()
    if org_request is None:
        raise SessionNotFoundError(f"Request '{request_id}' not found")
    if org_request.status != ORGANIZER_REQUEST_PENDING:
        raise RegistrationError(
            f"Request is already '{org_request.status}' and cannot be approved again"
        )

    # Create the organizer account. Use the email as username for simplicity.
    new_user = User(
        username=org_request.email,
        email=org_request.email,
        password_hash=org_request.password_hash,
        role="ORGANIZER",
        status=USER_STATUS_ACTIVE,
        first_name=org_request.first_name,
        last_name=org_request.last_name,
        phone_number=org_request.phone_number,
    )
    db.add(new_user)
    await db.flush()  # get new_user.id before committing

    org_request.status = ORGANIZER_REQUEST_APPROVED
    org_request.reviewed_at = datetime.now(timezone.utc)
    org_request.reviewed_by = current_user.id
    org_request.user_id = new_user.id

    await db.commit()
    await db.refresh(org_request)

    await notifications.notify(OrganizerApproved(to_email=org_request.email))

    return _request_response(org_request)


@router.post("/{request_id}/reject", response_model=OrganizerRequestResponse)
async def reject_organizer_request(
    request_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    notifications: NotificationService = Depends(get_notification_service),
):
    req_uuid = parse_uuid(request_id, SessionNotFoundError, f"Request '{request_id}' not found")
    result = await db.execute(select(OrganizerRequest).where(OrganizerRequest.id == req_uuid))
    org_request = result.scalar_one_or_none()
    if org_request is None:
        raise SessionNotFoundError(f"Request '{request_id}' not found")
    if org_request.status != ORGANIZER_REQUEST_PENDING:
        raise RegistrationError(
            f"Request is already '{org_request.status}' and cannot be rejected again"
        )

    org_request.status = ORGANIZER_REQUEST_REJECTED
    org_request.reviewed_at = datetime.now(timezone.utc)
    org_request.reviewed_by = current_user.id

    await db.commit()
    await db.refresh(org_request)

    await notifications.notify(OrganizerRejected(to_email=org_request.email))

    return _request_response(org_request)
