"""Contest lifecycle endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import epic_core.registry as registry_module
from epic_api.dependencies import get_engine, require_organizer_or_admin
from epic_api.utils import get_contest_or_raise
from epic_core.db.models import Contest, SimulationSession, User
from epic_core.db.session import get_db, get_session_factory
from epic_core.engine import SimulationEngine
from epic_core.exceptions import (
    ContestStateError,
    EPICValidationError,
    InsufficientPermissionsError,
)

router = APIRouter(prefix="/contests", tags=["contests"])

ALLOWED_TRANSITIONS = {
    ("DRAFT", "SCHEDULED"),
    ("DRAFT", "ACTIVE"),
    ("SCHEDULED", "ACTIVE"),
    ("ACTIVE", "CLOSED"),
    ("CLOSED", "ARCHIVED"),
}
ALLOWED_VISIBILITIES = {"PUBLIC", "PRIVATE", "INVITATION_ONLY"}
ALLOWED_TASK_TYPES = {"FORECASTING"}


class CreateContestRequest(BaseModel):
    name: str
    description: str | None = None
    visibility: str = "PUBLIC"
    task_type: str = "FORECASTING"
    forecast_horizons: list[int] = Field(default_factory=lambda: [1, 5, 10])
    twin_id: str
    sensor_configs: list[dict] = Field(default_factory=lambda: [{"sensor_id": "position"}])
    fault_schedule: list[dict] = Field(default_factory=list)
    initial_conditions: dict | None = None
    sampling_rate_hz: float
    start_date: datetime
    end_date: datetime


class UpdateContestRequest(BaseModel):
    status: str | None = None
    end_date: datetime | None = None


def contest_response(contest: Contest) -> dict:
    return {
        "contest_id": str(contest.id),
        "name": contest.name,
        "description": contest.description,
        "status": contest.status,
        "visibility": contest.visibility,
        "twin_id": contest.twin_id,
        "sensor_configs": contest.sensor_configs,
        "fault_schedule": contest.fault_schedule,
        "initial_conditions": contest.initial_conditions,
        "sampling_rate_hz": contest.sampling_rate_hz,
        "start_date": contest.start_date,
        "end_date": contest.end_date,
        "created_by": str(contest.created_by) if contest.created_by else None,
        "created_at": contest.created_at,
    }


def validate_twin_config(
    twin_id: str,
    sensor_configs: list[dict],
    fault_schedule: list[dict],
) -> None:
    twin = registry_module.twin_registry.get(twin_id)
    supported_quantities = twin.supported_quantities()
    for sensor_config in sensor_configs:
        sensor_id = sensor_config.get("sensor_id")
        if not sensor_id:
            raise EPICValidationError("sensor config must include sensor_id")
        sensor = registry_module.sensor_registry.get(sensor_id)
        if sensor.measured_quantity not in supported_quantities:
            raise EPICValidationError(
                f"sensor '{sensor_id}' is not compatible with twin '{twin_id}'"
            )

    available_faults = {fault.fault_id for fault in twin.get_faults()}
    for entry in fault_schedule:
        fault_id = entry.get("fault_id")
        if not fault_id:
            raise EPICValidationError("fault schedule entry must include fault_id")
        if fault_id not in available_faults:
            raise EPICValidationError(
                f"fault '{fault_id}' is not available for twin '{twin_id}'"
            )


def validate_visibility(visibility: str) -> None:
    if visibility not in ALLOWED_VISIBILITIES:
        raise EPICValidationError(f"visibility '{visibility}' is not supported")


def validate_task_type(task_type: str) -> None:
    if task_type not in ALLOWED_TASK_TYPES:
        raise EPICValidationError(f"task_type '{task_type}' is not supported")


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contest(
    request: CreateContestRequest,
    current_user: User = Depends(require_organizer_or_admin),
    db: AsyncSession = Depends(get_db),
):
    validate_twin_config(request.twin_id, request.sensor_configs, request.fault_schedule)
    validate_visibility(request.visibility)
    validate_task_type(request.task_type)
    if request.end_date <= request.start_date:
        raise EPICValidationError("end_date must be after start_date")

    contest = Contest(
        name=request.name,
        description=request.description,
        status="DRAFT",
        visibility=request.visibility,
        task_type=request.task_type,
        forecast_horizons=request.forecast_horizons,
        twin_id=request.twin_id,
        sensor_configs=request.sensor_configs,
        fault_schedule=request.fault_schedule,
        initial_conditions=request.initial_conditions,
        sampling_rate_hz=request.sampling_rate_hz,
        start_date=request.start_date,
        end_date=request.end_date,
        created_by=current_user.id,
    )
    db.add(contest)
    await db.commit()
    await db.refresh(contest)
    return contest_response(contest)


@router.get("")
async def list_contests(
    status: str | None = Query(None),
    visibility: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Contest)
    count_query = select(func.count()).select_from(Contest)
    if status is not None:
        query = query.where(Contest.status == status)
        count_query = count_query.where(Contest.status == status)
    if visibility is not None:
        query = query.where(Contest.visibility == visibility)
        count_query = count_query.where(Contest.visibility == visibility)

    total_result = await db.execute(count_query)
    result = await db.execute(query.offset(offset).limit(limit))
    return {
        "total": total_result.scalar_one(),
        "contests": [contest_response(contest) for contest in result.scalars()],
    }


@router.get("/{contest_id}")
async def get_contest(
    contest_id: str,
    db: AsyncSession = Depends(get_db),
):
    contest = await get_contest_or_raise(db, contest_id)
    return contest_response(contest)


@router.patch("/{contest_id}")
async def update_contest(
    contest_id: str,
    request: UpdateContestRequest,
    current_user: User = Depends(require_organizer_or_admin),
    db: AsyncSession = Depends(get_db),
    engine: SimulationEngine = Depends(get_engine),
):
    contest = await get_contest_or_raise(db, contest_id)
    if current_user.role == "ORGANIZER" and contest.created_by != current_user.id:
        raise InsufficientPermissionsError(
            "Organizers can only modify their own contests"
        )

    if request.status is None and request.end_date is None:
        raise EPICValidationError("Request must include status or end_date")

    target_status = request.status
    if target_status is not None and (
        contest.status,
        target_status,
    ) not in ALLOWED_TRANSITIONS:
        raise ContestStateError(
            f"Cannot transition contest from {contest.status} to {target_status}"
        )

    if request.end_date is not None:
        deadline_status = target_status or contest.status
        if deadline_status not in {"ACTIVE", "SCHEDULED"}:
            raise ContestStateError(
                "Deadline can only be extended on ACTIVE or SCHEDULED contests"
            )
        if as_utc(request.end_date) <= datetime.now(timezone.utc):
            raise EPICValidationError("end_date must be in the future")
        contest.end_date = request.end_date

    if target_status is not None:
        if target_status == "ACTIVE":
            validate_twin_config(
                contest.twin_id,
                contest.sensor_configs,
                contest.fault_schedule,
            )
            session = SimulationSession(
                contest_id=contest.id,
                twin_id=contest.twin_id,
                sampling_rate_hz=contest.sampling_rate_hz,
            )
            db.add(session)
            await db.commit()
            asyncio.create_task(
                engine.run_session(str(session.id), get_session_factory())
            )

        if target_status == "CLOSED":
            contest.end_date = datetime.now(timezone.utc)

        contest.status = target_status

    await db.commit()
    await db.refresh(contest)
    return contest_response(contest)
