"""Simulation session endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import epic_core.registry as registry_module
from epic_api.dependencies import get_current_user, get_engine
from epic_core.db.models import SensorObservation, SimulationSession, User
from epic_core.db.session import get_db, get_session_factory
from epic_core.engine import SimulationEngine
from epic_core.exceptions import (
    EPICValidationError,
    InsufficientPermissionsError,
    PluginNotFoundError,
    SessionNotFoundError,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    twin_id: str
    scenario_id: str
    mode: str
    duration_seconds: float
    sampling_rate_hz: float
    seed: int | None = None


def session_response(session: SimulationSession) -> dict:
    return {
        "id": str(session.id),
        "user_id": str(session.user_id),
        "twin_id": session.twin_id,
        "scenario_id": session.scenario_id,
        "mode": session.mode,
        "status": session.status,
        "sampling_rate_hz": session.sampling_rate_hz,
        "duration_seconds": session.duration_seconds,
        "seed": session.seed,
        "created_at": session.created_at,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    engine: SimulationEngine = Depends(get_engine),
):
    twin = registry_module.twin_registry.get(request.twin_id)
    if request.scenario_id not in {
        scenario.scenario_id for scenario in twin.get_scenarios()
    }:
        raise EPICValidationError(
            f"Scenario '{request.scenario_id}' is not available for twin '{request.twin_id}'"
        )
    if request.mode not in {"TRAINING", "VALIDATION", "TEST"}:
        raise EPICValidationError("mode must be one of TRAINING, VALIDATION, TEST")

    simulation_session = SimulationSession(
        user_id=current_user.id,
        twin_id=request.twin_id,
        scenario_id=request.scenario_id,
        mode=request.mode,
        duration_seconds=request.duration_seconds,
        sampling_rate_hz=request.sampling_rate_hz,
        seed=request.seed,
    )
    db.add(simulation_session)
    await db.commit()
    await db.refresh(simulation_session)

    asyncio.create_task(
        engine.run_session(str(simulation_session.id), get_session_factory())
    )
    return session_response(simulation_session)


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    simulation_session = await _get_authorized_session(session_id, current_user, db)
    return session_response(simulation_session)


@router.get("/{session_id}/observations")
async def list_observations(
    session_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    simulation_session = await _get_authorized_session(session_id, current_user, db)
    query = select(SensorObservation).where(
        SensorObservation.session_id == simulation_session.id
    )
    count_query = select(func.count()).select_from(SensorObservation).where(
        SensorObservation.session_id == simulation_session.id
    )
    if from_timestamp is not None:
        query = query.where(SensorObservation.timestamp >= from_timestamp)
        count_query = count_query.where(SensorObservation.timestamp >= from_timestamp)
    if to_timestamp is not None:
        query = query.where(SensorObservation.timestamp <= to_timestamp)
        count_query = count_query.where(SensorObservation.timestamp <= to_timestamp)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(SensorObservation.sequence_id).offset(offset).limit(limit)
    )
    observations = result.scalars().all()

    return {
        "session_id": session_id,
        "total": total,
        "observations": [
            {
                "sequence_id": observation.sequence_id,
                "timestamp": observation.timestamp.isoformat(),
                "sensors": observation.sensors,
                "labels": observation.labels,
            }
            for observation in observations
        ],
    }


async def _get_authorized_session(
    session_id: str, current_user: User, db: AsyncSession
) -> SimulationSession:
    try:
        session_uuid = UUID(session_id)
    except ValueError as exc:
        raise SessionNotFoundError(f"Session '{session_id}' does not exist") from exc

    result = await db.execute(
        select(SimulationSession).where(SimulationSession.id == session_uuid)
    )
    simulation_session = result.scalar_one_or_none()
    if simulation_session is None:
        raise SessionNotFoundError(f"Session '{session_id}' does not exist")
    if simulation_session.user_id != current_user.id and current_user.role != "ADMINISTRATOR":
        raise InsufficientPermissionsError("Cannot access another user's session")
    return simulation_session

