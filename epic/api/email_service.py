"""SMTP-backed NotificationService implementation.

EmailNotificationService is the production delivery adapter.
It is wired via the get_notification_service() FastAPI dependency;
tests and unconfigured deployments use NullNotificationService instead.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from epic.core.config import Settings
from epic.core.db.models import INVITATION_TOKEN_TTL_DAYS
from epic.core.notifications import NotificationEvent, NotificationService

logger = logging.getLogger(__name__)

# event_type → template file. Adding a notification = one event class in
# epic/core/notifications.py plus one template file here.
_TEMPLATES = {
    "organizer_request_received": "organizer_request_received.txt",
    "organizer_approved": "organizer_approved.txt",
    "organizer_rejected": "organizer_rejected.txt",
    "participant_invitation": "participant_invitation.txt",
    "contest_created": "contest_created.txt",
    "submission_received": "submission_received.txt",
    "participant_registered": "participant_registered.txt",
    "invitation_accepted": "invitation_accepted.txt",
    "session_failed": "session_failed.txt",
    "session_auto_paused": "session_auto_paused.txt",
    "submission_window_open": "submission_window_open.txt",
}

_TEMPLATES_DIR = Path(__file__).parent / "email_templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape([]),  # plain-text only
    keep_trailing_newline=True,
)


def _render(template_name: str, **context: object) -> tuple[str, str]:
    """Render a template and return (subject, body).

    The first line of every template is 'Subject: <text>'; the rest is the body.
    """
    raw = _jinja_env.get_template(template_name).render(**context)
    lines = raw.splitlines(keepends=True)
    subject_line = lines[0].strip()
    subject = subject_line.removeprefix("Subject:").strip()
    body = "".join(lines[1:]).lstrip("\n")
    return subject, body


class EmailNotificationService(NotificationService):
    """Delivers notifications via SMTP using aiosmtplib.

    All methods are fire-and-forget: delivery errors are logged but never
    re-raised, so a mail outage never disrupts the registration workflow.
    """

    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = settings.smtp_password
        self._sender = settings.smtp_sender or settings.admin_email or "noreply@epic.local"
        self._tls = settings.smtp_tls
        self._base_url = settings.base_url.rstrip("/")

    async def _send(self, *, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            async with aiosmtplib.SMTP(
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                start_tls=self._tls,
            ) as smtp:
                await smtp.sendmail(
                    sender=self._sender,
                    recipients=[to],
                    message=msg.as_string(),
                )
        except Exception:
            logger.exception("Failed to send email to %s (subject: %s)", to, subject)

    async def notify(self, event: NotificationEvent) -> None:
        template = _TEMPLATES.get(event.event_type)
        if template is None:
            logger.warning("No email template for event type '%s'", event.event_type)
            return
        context = {
            **event.context(),
            "base_url": self._base_url,
            "expiry_days": INVITATION_TOKEN_TTL_DAYS,
            "organizer_email": event.to_email,  # legacy template variable
        }
        subject, body = _render(template, **context)
        await self._send(to=event.to_email, subject=subject, body=body)
