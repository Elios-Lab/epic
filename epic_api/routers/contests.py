"""Contest lifecycle endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

import epic_core.registry as registry_module
from epic_api.dependencies import get_engine, require_admin, require_organizer_or_admin
from epic_api.utils import get_contest_or_raise
from epic_core.db.models import (
    Contest,
    ContestRegistration,
    LeaderboardEntry,
    Score,
    SensorObservation,
    SimulationSession,
    Submission,
    Task,
    User,
)
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
    ("PAUSED", "CLOSED"),   # close without resuming
    ("CLOSED", "ARCHIVED"),
}
# Pause and resume are handled by dedicated PUT endpoints, not via PATCH.
ALLOWED_VISIBILITIES = {"PUBLIC", "PRIVATE", "INVITATION_ONLY"}
ALLOWED_TASK_TYPES = {"FORECASTING"}


class CreateContestRequest(BaseModel):
    name: str
    description: str | None = None
    visibility: str = "PUBLIC"
    task_type: str = "FORECASTING"
    metric_ids: list[str] = Field(default_factory=lambda: ["mae"])
    twin_id: str
    sensor_configs: list[dict] = Field(default_factory=lambda: [{"sensor_id": "position"}])
    fault_schedule: list[dict] = Field(default_factory=list)
    initial_conditions: dict | None = None
    sampling_rate_hz: float
    start_date: datetime
    end_date: datetime
    end_of_observation: datetime | None = None
    prediction_horizon_seconds: float | None = None
    score_against: str = "ground_truth"  # "ground_truth" | "sensors"


class UpdateContestRequest(BaseModel):
    status: str | None = None
    end_date: datetime | None = None


def task_response(task: Task) -> dict:
    return {
        "task_id": str(task.id),
        "task_type": task.task_type,
        "name": task.name,
        "weight": task.weight,
        "configuration": task.configuration,
    }


def contest_response(contest: Contest, tasks: list[Task] | None = None) -> dict:
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
        "end_of_observation": contest.end_of_observation,
        "prediction_horizon_seconds": contest.prediction_horizon_seconds,
        "created_by": str(contest.created_by) if contest.created_by else None,
        "created_at": contest.created_at,
        "tasks": [task_response(task) for task in tasks or []],
    }


async def load_contest_tasks(db: AsyncSession, contest: Contest) -> list[Task]:
    result = await db.execute(select(Task).where(Task.contest_id == contest.id))
    return list(result.scalars())


async def load_tasks_for_contests(
    db: AsyncSession, contest_ids: list[UUID]
) -> dict[UUID, list[Task]]:
    if not contest_ids:
        return {}
    result = await db.execute(select(Task).where(Task.contest_id.in_(contest_ids)))
    tasks_by_contest: dict[UUID, list[Task]] = {}
    for task in result.scalars():
        tasks_by_contest.setdefault(task.contest_id, []).append(task)
    return tasks_by_contest


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
    existing = await db.execute(select(Contest).where(Contest.name == request.name))
    if existing.scalar_one_or_none() is not None:
        raise EPICValidationError(f"A contest named '{request.name}' already exists.")

    validate_twin_config(request.twin_id, request.sensor_configs, request.fault_schedule)
    validate_visibility(request.visibility)
    validate_task_type(request.task_type)
    if request.end_date <= request.start_date:
        raise EPICValidationError("end_date must be after start_date")

    # Both end_of_observation and prediction_horizon_seconds are required
    if request.end_of_observation is None or request.prediction_horizon_seconds is None:
        raise EPICValidationError(
            "end_of_observation and prediction_horizon_seconds are required"
        )
    if request.prediction_horizon_seconds <= 0:
        raise EPICValidationError("prediction_horizon_seconds must be positive")
    if as_utc(request.end_of_observation) <= as_utc(request.start_date):
        raise EPICValidationError("end_of_observation must be after start_date")
    from datetime import timedelta
    end_of_evaluation = as_utc(request.end_of_observation) + timedelta(
        seconds=request.prediction_horizon_seconds
    )
    if as_utc(request.end_date) <= end_of_evaluation:
        raise EPICValidationError(
            "end_date must be after end_of_observation + prediction_horizon_seconds "
            "(leave time for participants to submit)"
        )
    if request.prediction_horizon_seconds * request.sampling_rate_hz < 1:
        raise EPICValidationError(
            "prediction_horizon_seconds is too short for the configured sampling_rate_hz"
        )

    # Validate metric_ids
    if not request.metric_ids:
        raise EPICValidationError("metric_ids must contain at least one metric")
    for mid in request.metric_ids:
        if not registry_module.metric_registry.contains(mid):
            raise EPICValidationError(f"metric '{mid}' is not registered")

    # Validate score_against
    if request.score_against not in ("ground_truth", "sensors"):
        raise EPICValidationError(
            "score_against must be 'ground_truth' or 'sensors'"
        )

    contest = Contest(
        name=request.name,
        description=request.description,
        status="DRAFT",
        visibility=request.visibility,
        twin_id=request.twin_id,
        sensor_configs=request.sensor_configs,
        fault_schedule=request.fault_schedule,
        initial_conditions=request.initial_conditions,
        sampling_rate_hz=request.sampling_rate_hz,
        start_date=request.start_date,
        end_date=request.end_date,
        end_of_observation=request.end_of_observation,
        prediction_horizon_seconds=request.prediction_horizon_seconds,
        created_by=current_user.id,
    )
    db.add(contest)
    await db.flush()

    task_config: dict = {
        "prediction_horizon_seconds": request.prediction_horizon_seconds,
        "eval_steps": round(request.prediction_horizon_seconds * request.sampling_rate_hz),
        "score_against": request.score_against,
    }
    task = Task(
        contest_id=contest.id,
        task_type=request.task_type,
        name=request.task_type,
        metric_ids=request.metric_ids,
        weight=1.0,
        configuration=task_config,
    )
    db.add(task)
    await db.commit()
    await db.refresh(contest)
    await db.refresh(task)
    return contest_response(contest, [task])


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
    contests = list(result.scalars())
    tasks_by_contest = await load_tasks_for_contests(db, [c.id for c in contests])
    return {
        "total": total_result.scalar_one(),
        "contests": [
            contest_response(contest, tasks_by_contest.get(contest.id, []))
            for contest in contests
        ],
    }


@router.get("/{contest_id}")
async def get_contest(
    contest_id: str,
    db: AsyncSession = Depends(get_db),
):
    contest = await get_contest_or_raise(db, contest_id)
    return contest_response(contest, await load_contest_tasks(db, contest))


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
        if deadline_status not in {"ACTIVE", "SCHEDULED", "PAUSED"}:
            raise ContestStateError(
                "Deadline can only be extended on ACTIVE, SCHEDULED, or PAUSED contests"
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

        if target_status == "CLOSED":
            contest.end_date = datetime.now(timezone.utc)

        contest.status = target_status

    await db.commit()

    if target_status == "ACTIVE":
        asyncio.create_task(
            engine.run_session(str(session.id), get_session_factory())
        )
    await db.refresh(contest)
    return contest_response(contest, await load_contest_tasks(db, contest))


@router.delete("/{contest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contest(
    contest_id: str,
    current_user: User = Depends(require_organizer_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete a contest and all associated data:
    sensor observations, scores, leaderboard entries, submissions,
    registrations, simulation sessions, and tasks.

    ADMINISTRATOR may delete any contest.
    ORGANIZER may delete only their own contests.
    ACTIVE contests cannot be deleted — close them first.
    """
    contest = await get_contest_or_raise(db, contest_id)

    if current_user.role == "ORGANIZER" and contest.created_by != current_user.id:
        raise InsufficientPermissionsError(
            "Organizers can only delete their own contests"
        )

    if contest.status == "ACTIVE":
        raise ContestStateError(
            "Cannot delete an ACTIVE contest — close it first "
            "(PATCH status to CLOSED), then delete."
        )

    # ── Collect child IDs needed for grandchild deletion ──────────────
    session_ids_result = await db.execute(
        select(SimulationSession.id).where(SimulationSession.contest_id == contest.id)
    )
    session_ids = [row[0] for row in session_ids_result]

    submission_ids_result = await db.execute(
        select(Submission.id).where(Submission.contest_id == contest.id)
    )
    submission_ids = [row[0] for row in submission_ids_result]

    # ── Delete in bottom-up dependency order ──────────────────────────
    # 1. SensorObservation  (FK → simulation_sessions.id)
    if session_ids:
        await db.execute(
            delete(SensorObservation).where(
                SensorObservation.session_id.in_(session_ids)
            )
        )

    # 2. Score  (FK → submissions.id)
    if submission_ids:
        await db.execute(
            delete(Score).where(Score.submission_id.in_(submission_ids))
        )

    # 3. LeaderboardEntry  (FK → contests.id)
    await db.execute(
        delete(LeaderboardEntry).where(LeaderboardEntry.contest_id == contest.id)
    )

    # 4. Submission  (FK → contests.id)
    await db.execute(
        delete(Submission).where(Submission.contest_id == contest.id)
    )

    # 5. ContestRegistration  (FK → contests.id)
    await db.execute(
        delete(ContestRegistration).where(ContestRegistration.contest_id == contest.id)
    )

    # 6. SimulationSession  (FK → contests.id)
    await db.execute(
        delete(SimulationSession).where(SimulationSession.contest_id == contest.id)
    )

    # 7. Task  (FK → contests.id)
    await db.execute(
        delete(Task).where(Task.contest_id == contest.id)
    )

    # 8. Contest itself
    await db.delete(contest)
    await db.commit()


@router.put("/{contest_id}/pause", status_code=status.HTTP_200_OK)
async def pause_contest(
    contest_id: str,
    current_user: User = Depends(require_organizer_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Pause a running contest.

    Sets the contest status to PAUSED.  The simulation engine detects this
    on its next periodic DB check (≤ commit_interval steps) and stops
    gracefully, preserving all observations produced so far.

    The contest can be resumed later via PUT /{contest_id}/resume.

    ORGANIZER may pause their own contests.  ADMINISTRATOR may pause any.
    Only ACTIVE contests may be paused.
    """
    contest = await get_contest_or_raise(db, contest_id)

    if current_user.role == "ORGANIZER" and contest.created_by != current_user.id:
        raise InsufficientPermissionsError("Organizers can only pause their own contests")

    if contest.status != "ACTIVE":
        raise ContestStateError(
            f"Cannot pause a contest in status '{contest.status}' — only ACTIVE contests can be paused"
        )

    contest.status = "PAUSED"
    await db.commit()
    return contest_response(contest, await load_contest_tasks(db, contest))


@router.put("/{contest_id}/resume", status_code=status.HTTP_200_OK)
async def resume_contest(
    contest_id: str,
    current_user: User = Depends(require_organizer_or_admin),
    db: AsyncSession = Depends(get_db),
    engine: SimulationEngine = Depends(get_engine),
):
    """
    Resume a paused contest.

    Sets the contest status back to ACTIVE and restarts the simulation engine
    on the existing session.  The engine continues from the last committed
    sequence_id, so participants receive a continuous observation stream
    with no duplicate sequence numbers.  The twin is re-initialized from its
    initial conditions (physics restarts), but observation history is preserved.

    The contest end_date must still be in the future.  If it has passed, extend
    it via PATCH /{contest_id} before resuming.

    ORGANIZER may resume their own contests.  ADMINISTRATOR may resume any.
    Only PAUSED contests may be resumed.
    """
    contest = await get_contest_or_raise(db, contest_id)

    if current_user.role == "ORGANIZER" and contest.created_by != current_user.id:
        raise InsufficientPermissionsError("Organizers can only resume their own contests")

    if contest.status != "PAUSED":
        raise ContestStateError(
            f"Cannot resume a contest in status '{contest.status}' — only PAUSED contests can be resumed"
        )

    if contest.end_date and as_utc(contest.end_date) <= datetime.now(timezone.utc):
        raise ContestStateError(
            "Contest end_date has passed — extend the deadline "
            "(PATCH end_date) before resuming"
        )

    result = await db.execute(
        select(SimulationSession).where(SimulationSession.contest_id == contest.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise ContestStateError("No simulation session found for this contest")

    # Reactivate the existing session so the engine can attach to it.
    session.status = "RUNNING"
    session.started_at = datetime.now(timezone.utc)
    session.ended_at = None

    contest.status = "ACTIVE"
    await db.commit()

    asyncio.create_task(
        engine.run_session(str(session.id), get_session_factory())
    )

    await db.refresh(contest)
    return contest_response(contest, await load_contest_tasks(db, contest))
