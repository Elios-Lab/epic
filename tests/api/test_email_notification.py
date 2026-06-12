"""Tests for EmailNotificationService.

aiosmtplib.SMTP is mocked so no real mail server is needed.
Each test verifies that the correct SMTP calls are made for a given
notification type, and that delivery errors are swallowed silently.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from epic.api.email_service import EmailNotificationService
from epic.api.dependencies import get_notification_service
from epic.core.config import Settings
from epic.core.notifications import (
    ContestCreated,
    NullNotificationService,
    OrganizerApproved,
    OrganizerRejected,
    OrganizerRequestReceived,
    ParticipantInvitation,
    SessionFailed,
    SubmissionReceived,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_settings(**overrides) -> Settings:
    base = dict(
        database_url="sqlite+aiosqlite:///:memory:",
        secret_key="test-secret-key-32-characters-xx",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="user@example.com",
        smtp_password="secret",
        smtp_sender="noreply@epic.example.com",
        smtp_tls=True,
    )
    base.update(overrides)
    return Settings(**base)


def _smtp_patch():
    """Return a context manager that patches aiosmtplib.SMTP with an async mock."""
    smtp_instance = AsyncMock()
    smtp_instance.__aenter__ = AsyncMock(return_value=smtp_instance)
    smtp_instance.__aexit__ = AsyncMock(return_value=False)
    return patch("epic.api.email_service.aiosmtplib.SMTP", return_value=smtp_instance), smtp_instance


# ── Dependency auto-selection ─────────────────────────────────────────────────

def test_get_notification_service_returns_null_when_smtp_not_configured():
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        secret_key="test-secret-key-32-characters-xx",
    )
    service = get_notification_service(settings=settings)
    assert isinstance(service, NullNotificationService)


def test_get_notification_service_returns_email_when_smtp_configured():
    settings = _make_settings()
    service = get_notification_service(settings=settings)
    assert isinstance(service, EmailNotificationService)


# ── OrganizerRequestReceived ────────────────────────────────────────

@pytest.mark.asyncio
async def test_organizer_request_received_sends_email_to_admin():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(OrganizerRequestReceived(
            to_email="admin@epic.example.com",
            request_id="abc-123",
            requester_email="alice@example.com",
        ))

    smtp.sendmail.assert_awaited_once()
    call_kwargs = smtp.sendmail.call_args
    assert call_kwargs.kwargs["recipients"] == ["admin@epic.example.com"]


@pytest.mark.asyncio
async def test_organizer_request_received_body_contains_requester_email():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(OrganizerRequestReceived(
            to_email="admin@epic.example.com",
            request_id="abc-123",
            requester_email="alice@example.com",
        ))

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "alice@example.com" in message_str


@pytest.mark.asyncio
async def test_organizer_request_received_body_contains_request_id():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(OrganizerRequestReceived(
            to_email="admin@epic.example.com",
            request_id="abc-123",
            requester_email="alice@example.com",
        ))

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "abc-123" in message_str


# ── OrganizerApproved ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_organizer_approved_sends_email_to_organizer():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(OrganizerApproved(to_email="alice@example.com"))

    smtp.sendmail.assert_awaited_once()
    assert smtp.sendmail.call_args.kwargs["recipients"] == ["alice@example.com"]


@pytest.mark.asyncio
async def test_organizer_approved_body_indicates_approval():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(OrganizerApproved(to_email="alice@example.com"))

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "approved" in message_str.lower()


# ── OrganizerRejected ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_organizer_rejected_sends_email_to_organizer():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(OrganizerRejected(to_email="alice@example.com"))

    smtp.sendmail.assert_awaited_once()
    assert smtp.sendmail.call_args.kwargs["recipients"] == ["alice@example.com"]


@pytest.mark.asyncio
async def test_organizer_rejected_body_indicates_rejection():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(OrganizerRejected(to_email="alice@example.com"))

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "not" in message_str.lower() or "rejected" in message_str.lower() or "unable" in message_str.lower()


# ── ParticipantInvitation ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_participant_invitation_sends_email_to_invitee():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(ParticipantInvitation(
            to_email="bob@example.com",
            invitation_link="http://testserver/register?token=abc",
            contest_name="Test Contest",
        ))

    smtp.sendmail.assert_awaited_once()
    assert smtp.sendmail.call_args.kwargs["recipients"] == ["bob@example.com"]


@pytest.mark.asyncio
async def test_participant_invitation_body_contains_link_and_contest():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(ParticipantInvitation(
            to_email="bob@example.com",
            invitation_link="http://testserver/register?token=abc",
            contest_name="Test Contest",
        ))

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "http://testserver/register?token=abc" in message_str
    assert "Test Contest" in message_str


# ── Error handling ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_smtp_connection_error_is_swallowed():
    """Delivery failures must never propagate — fire and forget."""
    with patch("epic.api.email_service.aiosmtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = Exception("Connection refused")
        service = EmailNotificationService(_make_settings())
        # Must not raise
        await service.notify(OrganizerApproved(to_email="alice@example.com"))


@pytest.mark.asyncio
async def test_smtp_send_error_is_swallowed():
    ctx, smtp = _smtp_patch()
    smtp.sendmail.side_effect = Exception("Send failed")
    with ctx:
        service = EmailNotificationService(_make_settings())
        # Must not raise
        await service.notify(OrganizerApproved(to_email="alice@example.com"))


# ── SMTP connection settings ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_smtp_connects_with_configured_host_and_port():
    ctx, smtp = _smtp_patch()
    with ctx as mock_smtp_cls:
        service = EmailNotificationService(_make_settings(smtp_host="mail.example.com", smtp_port=465))
        await service.notify(OrganizerApproved(to_email="alice@example.com"))

    init_kwargs = mock_smtp_cls.call_args.kwargs
    assert init_kwargs["hostname"] == "mail.example.com"
    assert init_kwargs["port"] == 465


@pytest.mark.asyncio
async def test_smtp_uses_sender_from_settings():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings(smtp_sender="custom@sender.com"))
        await service.notify(OrganizerApproved(to_email="alice@example.com"))

    assert smtp.sendmail.call_args.kwargs["sender"] == "custom@sender.com"


# ── New event types ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_contest_created_email_to_admin():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(ContestCreated(
            to_email="admin@epic.example.com",
            contest_name="Pump Challenge",
            organizer_username="prof_rossi",
        ))

    assert smtp.sendmail.call_args.kwargs["recipients"] == ["admin@epic.example.com"]
    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "Pump Challenge" in message_str
    assert "prof_rossi" in message_str


@pytest.mark.asyncio
async def test_submission_received_email_to_organizer():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(SubmissionReceived(
            to_email="organizer@example.com",
            contest_name="Pump Challenge",
            participant_username="student1",
            submission_id="sub-42",
        ))

    assert smtp.sendmail.call_args.kwargs["recipients"] == ["organizer@example.com"]
    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "student1" in message_str and "sub-42" in message_str


@pytest.mark.asyncio
async def test_session_failed_email_contains_error():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(SessionFailed(
            to_email="organizer@example.com",
            contest_name="Pump Challenge",
            error="plugin error in step()",
        ))

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "plugin error in step()" in message_str
    assert "FAILED" in message_str


@pytest.mark.asyncio
async def test_unknown_event_type_is_ignored():
    """An event without a template must be logged and skipped, never raise."""
    from epic.core.notifications import NotificationEvent

    class FutureEvent(NotificationEvent):
        # Plain subclass shadowing event_type; inherits the dataclass __init__.
        event_type = "future_event"

    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify(FutureEvent(to_email="x@example.com"))

    smtp.sendmail.assert_not_awaited()


# ── Router integration (CollectingNotificationService via dependency override) ─

def test_contest_creation_notifies_admin(
    client, registered_contest, collecting_notifications
):
    """Creating a contest as an organizer must notify the administrator(s)."""
    from epic.core.notifications import ContestCreated as ContestCreatedEvent

    events = collecting_notifications.of_type(ContestCreatedEvent)
    assert len(events) == 1
    assert events[0].to_email == "admin@example.com"
    assert events[0].contest_name == "Test Contest"
    assert events[0].organizer_username == "organizer1"


def test_registration_notifies_contest_owner(
    client, registered_contest, organizer_headers, auth_headers, collecting_notifications
):
    """A participant registering must notify the contest's organizer."""
    from epic.core.notifications import ParticipantRegistered as RegisteredEvent

    # Registration requires a published contest; the fixture leaves it in DRAFT.
    publish = client.patch(
        f"/api/v1/contests/{registered_contest['contest_id']}",
        json={"status": "SCHEDULED"},
        headers=organizer_headers,
    )
    assert publish.status_code == 200

    response = client.post(
        "/api/v1/contest-registrations",
        json={"contest_id": registered_contest["contest_id"]},
        headers=auth_headers,
    )
    assert response.status_code == 201

    events = collecting_notifications.of_type(RegisteredEvent)
    assert len(events) == 1
    assert events[0].to_email == "organizer@example.com"
    assert events[0].contest_name == "Test Contest"
    assert events[0].participant_username == "student1"


def test_invitation_acceptance_notifies_inviter(
    client, registered_contest, organizer_headers, collecting_notifications
):
    """Accepting an invitation must notify the organizer who sent it."""
    from sqlalchemy import select as sa_select

    from epic.core.db.models import Invitation
    from epic.core.db.session import get_session_factory
    from epic.core.notifications import InvitationAccepted as AcceptedEvent

    client.post(
        f"/api/v1/contests/{registered_contest['contest_id']}/invitations",
        json={"emails": ["dora@example.com"]},
        headers=organizer_headers,
    )

    import asyncio as aio

    async def _token():
        async with get_session_factory()() as db:
            result = await db.execute(
                sa_select(Invitation).where(Invitation.email == "dora@example.com")
            )
            return result.scalar_one().token

    token = aio.run(_token())
    response = client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"first_name": "Dora", "last_name": "Verdi", "password": "dora-secret-99"},
    )
    assert response.status_code == 201

    events = collecting_notifications.of_type(AcceptedEvent)
    assert len(events) == 1
    assert events[0].to_email == "organizer@example.com"
    assert events[0].participant_email == "dora@example.com"
