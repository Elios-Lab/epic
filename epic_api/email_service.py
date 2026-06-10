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

from epic_core.config import Settings
from epic_core.db.models import INVITATION_TOKEN_TTL_DAYS
from epic_core.notifications import NotificationService

logger = logging.getLogger(__name__)

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

    async def notify_organizer_request_received(
        self, *, admin_email: str, request_id: str, requester_email: str
    ) -> None:
        subject, body = _render(
            "organizer_request_received.txt",
            request_id=request_id,
            requester_email=requester_email,
            base_url=self._base_url,
        )
        await self._send(to=admin_email, subject=subject, body=body)

    async def notify_organizer_approved(self, *, organizer_email: str) -> None:
        subject, body = _render(
            "organizer_approved.txt",
            organizer_email=organizer_email,
            base_url=self._base_url,
        )
        await self._send(to=organizer_email, subject=subject, body=body)

    async def notify_organizer_rejected(self, *, organizer_email: str) -> None:
        subject, body = _render("organizer_rejected.txt")
        await self._send(to=organizer_email, subject=subject, body=body)

    async def send_participant_invitation(
        self, *, to_email: str, invitation_link: str, contest_name: str
    ) -> None:
        subject, body = _render(
            "participant_invitation.txt",
            contest_name=contest_name,
            invitation_link=invitation_link,
            expiry_days=INVITATION_TOKEN_TTL_DAYS,
        )
        await self._send(to=to_email, subject=subject, body=body)
