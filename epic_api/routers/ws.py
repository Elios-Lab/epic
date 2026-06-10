"""WebSocket endpoints for contest streams."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_api.dependencies import get_broadcaster, get_settings
from epic_core.auth import decode_access_token
from epic_core.broadcaster import ContestBroadcaster
from epic_core.config import Settings
from epic_core.db.models import Contest, ContestRegistration
from epic_core.db.session import get_db
from epic_core.exceptions import InvalidCredentialsError

router = APIRouter()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.websocket("/contests/{contest_id}")
async def contest_stream(
    contest_id: str,
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
    broadcaster: ContestBroadcaster = Depends(get_broadcaster),
    settings: Settings = Depends(get_settings),
):
    try:
        token_payload = decode_access_token(token, settings)
        contest_uuid = UUID(contest_id)
        user_id = UUID(token_payload["sub"])
        role = token_payload.get("role")
    except (InvalidCredentialsError, ValueError, KeyError, TypeError):
        await websocket.close(code=1008)
        return

    result = await db.execute(select(Contest).where(Contest.id == contest_uuid))
    contest = result.scalar_one_or_none()
    if contest is None or contest.status != "ACTIVE":
        await websocket.close(code=1008)
        return

    # Authorization: administrators may monitor any contest; organizers only
    # their own; participants must hold an active registration.
    if role == "ADMINISTRATOR":
        pass
    elif role == "ORGANIZER":
        if contest.created_by != user_id:
            await websocket.close(code=1008)
            return
    else:
        registration_result = await db.execute(
            select(ContestRegistration).where(
                ContestRegistration.contest_id == contest_uuid,
                ContestRegistration.user_id == user_id,
                ContestRegistration.status == "REGISTERED",
            )
        )
        if registration_result.scalar_one_or_none() is None:
            await websocket.close(code=1008)
            return

    # In two-phase mode, reject connections once the evaluation phase has started.
    # Participants must not see the evaluation-phase sensor data.
    if (
        contest.end_of_observation is not None
        and datetime.now(timezone.utc) >= _as_utc(contest.end_of_observation)
    ):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    queue = broadcaster.subscribe(contest_id)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
            # The engine broadcasts a special "evaluation_started" event when
            # the observation phase ends.  Forward it to the client, then close
            # the stream — participants must not receive evaluation-phase data.
            if payload.get("event") in ("evaluation_started", "contest_closed"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe(contest_id, queue)
