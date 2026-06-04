"""Leaderboard endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_api.dependencies import get_current_user
from epic_api.utils import get_contest_or_raise, parse_uuid
from epic_core.db.models import LeaderboardEntry, User
from epic_core.db.session import get_db
from epic_core.exceptions import (
    ContestNotFoundError,
    InsufficientPermissionsError,
    RegistrationError,
)

router = APIRouter(prefix="/contests", tags=["leaderboard"])


def leaderboard_entry_response(entry: LeaderboardEntry, user: User) -> dict:
    return {
        "rank": entry.rank,
        "user_id": str(entry.user_id),
        "username": user.username,
        "submission_id": str(entry.submission_id),
        "score": entry.score,
        "updated_at": entry.updated_at.isoformat(),
    }


@router.get("/{contest_id}/leaderboard")
async def get_leaderboard(
    contest_id: str,
    db: AsyncSession = Depends(get_db),
):
    contest = await get_contest_or_raise(db, contest_id)
    result = await db.execute(
        select(LeaderboardEntry, User)
        .join(User, LeaderboardEntry.user_id == User.id)
        .where(LeaderboardEntry.contest_id == contest.id)
        .order_by(LeaderboardEntry.rank.asc())
    )
    return {
        "contest_id": str(contest.id),
        "entries": [
            leaderboard_entry_response(entry, user) for entry, user in result.all()
        ],
    }


@router.get("/{contest_id}/leaderboard/{user_id}")
async def get_user_leaderboard_entry(
    contest_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contest = await get_contest_or_raise(db, contest_id)
    target_user_id = parse_uuid(
        user_id,
        ContestNotFoundError,
        f"Leaderboard entry for user '{user_id}' does not exist",
    )
    if current_user.role == "PARTICIPANT" and current_user.id != target_user_id:
        raise InsufficientPermissionsError("Leaderboard access denied")
    if current_user.role == "ORGANIZER" and contest.created_by != current_user.username:
        raise InsufficientPermissionsError("Leaderboard access denied")

    result = await db.execute(
        select(LeaderboardEntry, User)
        .join(User, LeaderboardEntry.user_id == User.id)
        .where(
            LeaderboardEntry.contest_id == contest.id,
            LeaderboardEntry.user_id == target_user_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise RegistrationError("No leaderboard entry found")
    entry, user = row
    return leaderboard_entry_response(entry, user)
