"""WebSocket endpoints for contest streams."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from epic_api.dependencies import get_broadcaster, get_settings
from epic_core.auth import decode_access_token
from epic_core.broadcaster import ContestBroadcaster
from epic_core.config import Settings
from epic_core.db.models import Contest
from epic_core.db.session import get_db
from epic_core.exceptions import InvalidCredentialsError

router = APIRouter()


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
        decode_access_token(token, settings)
        contest_uuid = UUID(contest_id)
    except (InvalidCredentialsError, ValueError):
        await websocket.close(code=1008)
        return

    result = await db.execute(select(Contest).where(Contest.id == contest_uuid))
    contest = result.scalar_one_or_none()
    if contest is None or contest.status != "ACTIVE":
        await websocket.close(code=1008)
        return

    await websocket.accept()
    queue = broadcaster.subscribe(contest_id)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe(contest_id, queue)

