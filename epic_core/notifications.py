"""Notification service interface for EPIC Core.

The core emits notification calls; the delivery mechanism is injected
via a NotificationService implementation.  The core never depends on
a specific provider (SMTP, SendGrid, Slack, …).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationService(ABC):
    """Abstract notification service.

    All methods are fire-and-forget: they should not raise on delivery
    failure (log and swallow), so the calling business logic is never
    blocked by a notification outage.
    """

    @abstractmethod
    async def notify_organizer_request_received(self, *, admin_email: str, request_id: str, requester_email: str) -> None:
        """Notify the administrator that a new organizer registration request is pending."""

    @abstractmethod
    async def notify_organizer_approved(self, *, organizer_email: str) -> None:
        """Notify an organizer that their registration request was approved."""

    @abstractmethod
    async def notify_organizer_rejected(self, *, organizer_email: str) -> None:
        """Notify an organizer that their registration request was rejected."""

    @abstractmethod
    async def send_participant_invitation(self, *, to_email: str, invitation_link: str, contest_name: str) -> None:
        """Send a one-time invitation link to a prospective participant."""


class NullNotificationService(NotificationService):
    """No-op implementation.  Used in tests and when no provider is configured."""

    async def notify_organizer_request_received(self, *, admin_email: str, request_id: str, requester_email: str) -> None:
        pass

    async def notify_organizer_approved(self, *, organizer_email: str) -> None:
        pass

    async def notify_organizer_rejected(self, *, organizer_email: str) -> None:
        pass

    async def send_participant_invitation(self, *, to_email: str, invitation_link: str, contest_name: str) -> None:
        pass


class CollectingNotificationService(NotificationService):
    """In-memory implementation that records every call.  Useful in tests."""

    def __init__(self) -> None:
        self.organizer_requests_received: list[dict] = []
        self.organizer_approvals: list[str] = []
        self.organizer_rejections: list[str] = []
        self.participant_invitations: list[dict] = []

    async def notify_organizer_request_received(self, *, admin_email: str, request_id: str, requester_email: str) -> None:
        self.organizer_requests_received.append({
            "admin_email": admin_email,
            "request_id": request_id,
            "requester_email": requester_email,
        })

    async def notify_organizer_approved(self, *, organizer_email: str) -> None:
        self.organizer_approvals.append(organizer_email)

    async def notify_organizer_rejected(self, *, organizer_email: str) -> None:
        self.organizer_rejections.append(organizer_email)

    async def send_participant_invitation(self, *, to_email: str, invitation_link: str, contest_name: str) -> None:
        self.participant_invitations.append({
            "to_email": to_email,
            "invitation_link": invitation_link,
            "contest_name": contest_name,
        })
