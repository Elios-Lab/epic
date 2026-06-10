"""Tests for EmailNotificationService.

aiosmtplib.SMTP is mocked so no real mail server is needed.
Each test verifies that the correct SMTP calls are made for a given
notification type, and that delivery errors are swallowed silently.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from epic_api.email_service import EmailNotificationService
from epic_api.dependencies import get_notification_service
from epic_core.config import Settings
from epic_core.notifications import NullNotificationService


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
    return patch("epic_api.email_service.aiosmtplib.SMTP", return_value=smtp_instance), smtp_instance


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


# ── notify_organizer_request_received ────────────────────────────────────────

@pytest.mark.asyncio
async def test_organizer_request_received_sends_email_to_admin():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify_organizer_request_received(
            admin_email="admin@epic.example.com",
            request_id="abc-123",
            requester_email="alice@example.com",
        )

    smtp.sendmail.assert_awaited_once()
    call_kwargs = smtp.sendmail.call_args
    assert call_kwargs.kwargs["recipients"] == ["admin@epic.example.com"]


@pytest.mark.asyncio
async def test_organizer_request_received_body_contains_requester_email():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify_organizer_request_received(
            admin_email="admin@epic.example.com",
            request_id="abc-123",
            requester_email="alice@example.com",
        )

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "alice@example.com" in message_str


@pytest.mark.asyncio
async def test_organizer_request_received_body_contains_request_id():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify_organizer_request_received(
            admin_email="admin@epic.example.com",
            request_id="abc-123",
            requester_email="alice@example.com",
        )

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "abc-123" in message_str


# ── notify_organizer_approved ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_organizer_approved_sends_email_to_organizer():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify_organizer_approved(organizer_email="alice@example.com")

    smtp.sendmail.assert_awaited_once()
    assert smtp.sendmail.call_args.kwargs["recipients"] == ["alice@example.com"]


@pytest.mark.asyncio
async def test_organizer_approved_body_indicates_approval():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify_organizer_approved(organizer_email="alice@example.com")

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "approved" in message_str.lower()


# ── notify_organizer_rejected ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_organizer_rejected_sends_email_to_organizer():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify_organizer_rejected(organizer_email="alice@example.com")

    smtp.sendmail.assert_awaited_once()
    assert smtp.sendmail.call_args.kwargs["recipients"] == ["alice@example.com"]


@pytest.mark.asyncio
async def test_organizer_rejected_body_indicates_rejection():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.notify_organizer_rejected(organizer_email="alice@example.com")

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "not" in message_str.lower() or "rejected" in message_str.lower() or "unable" in message_str.lower()


# ── send_participant_invitation ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_participant_invitation_sends_email_to_invitee():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.send_participant_invitation(
            to_email="bob@example.com",
            invitation_link="http://testserver/register?token=abc",
            contest_name="Test Contest",
        )

    smtp.sendmail.assert_awaited_once()
    assert smtp.sendmail.call_args.kwargs["recipients"] == ["bob@example.com"]


@pytest.mark.asyncio
async def test_participant_invitation_body_contains_link_and_contest():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings())
        await service.send_participant_invitation(
            to_email="bob@example.com",
            invitation_link="http://testserver/register?token=abc",
            contest_name="Test Contest",
        )

    message_str = smtp.sendmail.call_args.kwargs["message"]
    assert "http://testserver/register?token=abc" in message_str
    assert "Test Contest" in message_str


# ── Error handling ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_smtp_connection_error_is_swallowed():
    """Delivery failures must never propagate — fire and forget."""
    with patch("epic_api.email_service.aiosmtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = Exception("Connection refused")
        service = EmailNotificationService(_make_settings())
        # Must not raise
        await service.notify_organizer_approved(organizer_email="alice@example.com")


@pytest.mark.asyncio
async def test_smtp_send_error_is_swallowed():
    ctx, smtp = _smtp_patch()
    smtp.sendmail.side_effect = Exception("Send failed")
    with ctx:
        service = EmailNotificationService(_make_settings())
        # Must not raise
        await service.notify_organizer_approved(organizer_email="alice@example.com")


# ── SMTP connection settings ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_smtp_connects_with_configured_host_and_port():
    ctx, smtp = _smtp_patch()
    with ctx as mock_smtp_cls:
        service = EmailNotificationService(_make_settings(smtp_host="mail.example.com", smtp_port=465))
        await service.notify_organizer_approved(organizer_email="alice@example.com")

    init_kwargs = mock_smtp_cls.call_args.kwargs
    assert init_kwargs["hostname"] == "mail.example.com"
    assert init_kwargs["port"] == 465


@pytest.mark.asyncio
async def test_smtp_uses_sender_from_settings():
    ctx, smtp = _smtp_patch()
    with ctx:
        service = EmailNotificationService(_make_settings(smtp_sender="custom@sender.com"))
        await service.notify_organizer_approved(organizer_email="alice@example.com")

    assert smtp.sendmail.call_args.kwargs["sender"] == "custom@sender.com"
