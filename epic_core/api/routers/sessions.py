"""Contest simulation session endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_core.api.dependencies import get_current_user
from epic_core.api.schemas import SessionResponse
from epic_core.kernel.db.models import Contest, SimulationSession, User
from epic_core.kernel.db.session import get_db
from epic_core.kernel.exceptions import ContestNotFoundError, SessionNotFoundError

router = APIRouter(prefix="/contests", tags=["sessions"])


def session_response(session: SimulationSession) -> dict:
    return {
        "session_id": str(session.id),
        "contest_id": str(session.contest_id),
        "twin_id": session.twin_id,
        "sampling_rate_hz": session.sampling_rate_hz,
        "status": session.status,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
    }


@router.get("/{contest_id}/session", response_model=SessionResponse)
async def get_contest_session(
    contest_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        contest_uuid = UUID(contest_id)
    except ValueError as exc:
        raise ContestNotFoundError(f"Contest '{contest_id}' does not exist") from exc

    contest_result = await db.execute(select(Contest).where(Contest.id == contest_uuid))
    contest = contest_result.scalar_one_or_none()
    if contest is None:
        raise ContestNotFoundError(f"Contest '{contest_id}' does not exist")

    session_result = await db.execute(
        select(SimulationSession).where(SimulationSession.contest_id == contest.id)
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise SessionNotFoundError(f"Contest '{contest_id}' has no session")

    return session_response(session)
