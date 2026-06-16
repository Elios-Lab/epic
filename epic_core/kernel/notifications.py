"""Notification service interface for EPIC Core.

The core and the API emit typed NotificationEvent objects; the delivery
mechanism is injected via a NotificationService implementation. The core
never depends on a specific provider (SMTP, SendGrid, Slack, …), and new
notification types are added by defining a new event class — the service
interface never changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, fields
from typing import ClassVar


# ── Events ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotificationEvent:
    """Base class for all notifications.

    Each event targets exactly one recipient; callers loop over recipients
    when an event fans out (e.g. all administrators). `event_type` is a
    stable identifier used by delivery adapters to select a template.
    """

    event_type: ClassVar[str] = ""

    to_email: str

    def context(self) -> dict:
        """Template context: every field except the recipient address."""
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name != "to_email"
        }


@dataclass(frozen=True)
class OrganizerRequestReceived(NotificationEvent):
    """A new organizer registration request is pending admin review."""

    event_type: ClassVar[str] = "organizer_request_received"
    request_id: str
    requester_email: str


@dataclass(frozen=True)
class OrganizerApproved(NotificationEvent):
    """An organizer registration request was approved."""

    event_type: ClassVar[str] = "organizer_approved"


@dataclass(frozen=True)
class OrganizerRejected(NotificationEvent):
    """An organizer registration request was rejected."""

    event_type: ClassVar[str] = "organizer_rejected"


@dataclass(frozen=True)
class ParticipantInvitation(NotificationEvent):
    """A one-time invitation link for a prospective participant."""

    event_type: ClassVar[str] = "participant_invitation"
    invitation_link: str
    contest_name: str


@dataclass(frozen=True)
class ContestCreated(NotificationEvent):
    """A new contest was created (sent to administrators)."""

    event_type: ClassVar[str] = "contest_created"
    contest_name: str
    organizer_username: str


@dataclass(frozen=True)
class SubmissionReceived(NotificationEvent):
    """A participant submitted a prediction (sent to the contest organizer)."""

    event_type: ClassVar[str] = "submission_received"
    contest_name: str
    participant_username: str
    submission_id: str


@dataclass(frozen=True)
class ParticipantRegistered(NotificationEvent):
    """A participant registered for a contest (sent to the organizer)."""

    event_type: ClassVar[str] = "participant_registered"
    contest_name: str
    participant_username: str


@dataclass(frozen=True)
class InvitationAccepted(NotificationEvent):
    """An invited participant completed registration (sent to the inviter)."""

    event_type: ClassVar[str] = "invitation_accepted"
    contest_name: str
    participant_email: str


@dataclass(frozen=True)
class SessionFailed(NotificationEvent):
    """A simulation session crashed (sent to organizer and administrators)."""

    event_type: ClassVar[str] = "session_failed"
    contest_name: str
    error: str


@dataclass(frozen=True)
class SessionAutoPaused(NotificationEvent):
    """A session was auto-paused by restart recovery (organizer + admins)."""

    event_type: ClassVar[str] = "session_auto_paused"
    contest_name: str


@dataclass(frozen=True)
class SubmissionWindowOpen(NotificationEvent):
    """The evaluation window ended; submissions are now accepted
    (sent to every registered participant)."""

    event_type: ClassVar[str] = "submission_window_open"
    contest_name: str


# ── Service interface ─────────────────────────────────────────────────────────


class NotificationService(ABC):
    """Abstract notification service.

    notify() is fire-and-forget: implementations must not raise on delivery
    failure (log and swallow), so the calling business logic is never
    blocked by a notification outage.
    """

    @abstractmethod
    async def notify(self, event: NotificationEvent) -> None:
        """Deliver one notification event to its recipient."""


class NullNotificationService(NotificationService):
    """No-op implementation. Used in tests and when no provider is configured."""

    async def notify(self, event: NotificationEvent) -> None:
        pass


class CollectingNotificationService(NotificationService):
    """In-memory implementation that records every event. Useful in tests.

    All events land in `self.events`; the legacy per-type lists for the
    original four notifications are kept in sync for existing tests.
    """

    def __init__(self) -> None:
        self.events: list[NotificationEvent] = []
        # Legacy views (kept in sync by notify()):
        self.organizer_requests_received: list[dict] = []
        self.organizer_approvals: list[str] = []
        self.organizer_rejections: list[str] = []
        self.participant_invitations: list[dict] = []

    def of_type(self, event_class: type) -> list[NotificationEvent]:
        return [event for event in self.events if isinstance(event, event_class)]

    async def notify(self, event: NotificationEvent) -> None:
        self.events.append(event)
        if isinstance(event, OrganizerRequestReceived):
            self.organizer_requests_received.append({
                "admin_email": event.to_email,
                "request_id": event.request_id,
                "requester_email": event.requester_email,
            })
        elif isinstance(event, OrganizerApproved):
            self.organizer_approvals.append(event.to_email)
        elif isinstance(event, OrganizerRejected):
            self.organizer_rejections.append(event.to_email)
        elif isinstance(event, ParticipantInvitation):
            self.participant_invitations.append({
                "to_email": event.to_email,
                "invitation_link": event.invitation_link,
                "contest_name": event.contest_name,
            })
