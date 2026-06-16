"""Shared API utilities."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_core.kernel.db.models import Contest
from epic_core.kernel.exceptions import ContestNotFoundError


def parse_uuid(value: str, error_cls, message: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise error_cls(message) from exc


async def get_contest_or_raise(db: AsyncSession, contest_id: str) -> Contest:
    contest_uuid = parse_uuid(
        contest_id,
        ContestNotFoundError,
        f"Contest '{contest_id}' does not exist",
    )
    result = await db.execute(select(Contest).where(Contest.id == contest_uuid))
    contest = result.scalar_one_or_none()
    if contest is None:
        raise ContestNotFoundError(f"Contest '{contest_id}' does not exist")
    return contest
