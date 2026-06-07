"""Submission endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import epic_core.registry as registry_module
from epic_api.dependencies import get_current_user
from epic_api.utils import get_contest_or_raise, parse_uuid
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
from epic_core.exceptions import (
    ContestStateError,
    InsufficientPermissionsError,
    RegistrationError,
    SubmissionError,
)

router = APIRouter(tags=["submissions"])


class CreateSubmissionRequest(BaseModel):
    task_id: str
    payload: dict


def submission_summary(submission: Submission) -> dict:
    return {
        "submission_id": str(submission.id),
        "user_id": str(submission.user_id),
        "task_id": submission.task_id,
        "submitted_at": submission.submitted_at.isoformat(),
        "status": submission.status,
    }


def submission_response(submission: Submission) -> dict:
    return {
        **submission_summary(submission),
        "contest_id": str(submission.contest_id),
        "payload": submission.payload,
        "submission_metadata": submission.submission_metadata,
    }


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _score_submission(
    submission_id: UUID, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    await asyncio.sleep(0.01)
    async with db_factory() as db:
        result = await db.execute(select(Submission).where(Submission.id == submission_id))
        submission = result.scalar_one_or_none()
        if submission is None:
            return
        contest_result = await db.execute(
            select(Contest).where(Contest.id == submission.contest_id)
        )
        contest = contest_result.scalar_one()
        task_result = await db.execute(
            select(Task).where(
                Task.contest_id == contest.id,
                Task.task_type == submission.task_id.upper(),
            )
        )
        task = task_result.scalars().first()
        if task is None:
            submission.status = "FAILED"
            submission.submission_metadata = {
                **(submission.submission_metadata or {}),
                "error": "Task not found for this contest",
            }
            await db.commit()
            return
        if task.task_type != "FORECASTING":
            submission.status = "FAILED"
            submission.submission_metadata = {
                **(submission.submission_metadata or {}),
                "error": f"Scoring for task type '{task.task_type}' is not yet implemented",
            }
            await db.commit()
            return

        metric_ids = task.metric_ids or ["mae"]
        score_values = await _score_two_phase(db, submission, contest, task, metric_ids)

        if score_values is None:
            # Scoring set PENDING or FAILED on the submission — already committed.
            return

        submission.status = "EVALUATED"
        await db.commit()
        if score_values:
            composite_score = sum(score_values) / len(score_values)
            await _update_leaderboard(
                submission.contest_id,
                submission.user_id,
                submission.id,
                composite_score,
                db_factory,
            )


async def _score_two_phase(
    db,
    submission: Submission,
    contest: Contest,
    task: Task,
    metric_ids: list[str],
) -> list[float] | None:
    """Score a two-phase submission against the full evaluation-window ground truth."""
    eval_steps = task.configuration.get("eval_steps")
    if not eval_steps:
        submission.status = "FAILED"
        submission.submission_metadata = {
            **(submission.submission_metadata or {}),
            "error": "Task configuration missing eval_steps",
        }
        await db.commit()
        return None

    # Retrieve all evaluation-phase observations ordered by sequence_id.
    obs_result = await db.execute(
        select(SensorObservation)
        .join(SimulationSession, SensorObservation.session_id == SimulationSession.id)
        .where(SimulationSession.contest_id == contest.id)
        .order_by(SensorObservation.sequence_id.asc())
    )
    eval_observations = list(obs_result.scalars())

    if len(eval_observations) < eval_steps:
        # Evaluation window not yet complete — defer.
        submission.status = "PENDING"
        await db.commit()
        return None

    # Use exactly eval_steps observations (the evaluation window).
    eval_observations = eval_observations[:eval_steps]

    # Parse and validate submission payload.
    try:
        forecast = submission.payload["forecast"]
        if not isinstance(forecast, dict):
            raise TypeError("payload.forecast must be a dict of {sensor_id: [values]}")
        sensor_ids = list(forecast.keys())
        for sid in sensor_ids:
            values = forecast[sid]
            if not isinstance(values, list) or len(values) != eval_steps:
                raise ValueError(
                    f"sensor '{sid}' must have exactly {eval_steps} predicted values, "
                    f"got {len(values) if isinstance(values, list) else type(values).__name__}"
                )
    except (KeyError, TypeError, ValueError) as exc:
        submission.status = "FAILED"
        submission.submission_metadata = {
            **(submission.submission_metadata or {}),
            "error": str(exc),
        }
        await db.commit()
        return None

    # Decide what to score against.
    # "ground_truth" uses the noiseless latent-state values stored by the engine.
    # "sensors"      uses the corrupted sensor readings (legacy / special cases).
    # If ground_truth was not recorded (old data or direct DB inserts in tests),
    # fall back to sensors automatically.
    score_against = task.configuration.get("score_against", "ground_truth")
    use_ground_truth = (
        score_against == "ground_truth"
        and eval_observations[0].ground_truth is not None
    )
    reference_key = "ground_truth" if use_ground_truth else "sensors"

    def _y_true(obs, sensor_id: str) -> float:
        source = obs.ground_truth if use_ground_truth else obs.sensors
        return float(source[sensor_id])

    def _sensor_available(sensor_id: str) -> bool:
        source = eval_observations[0].ground_truth if use_ground_truth else eval_observations[0].sensors
        return sensor_id in source

    # Compute all configured metrics for each sensor.
    score_values: list[float] = []
    for metric_id in metric_ids:
        metric = registry_module.metric_registry.get(metric_id)
        for sensor_id in sensor_ids:
            if not _sensor_available(sensor_id):
                continue
            y_true = [_y_true(obs, sensor_id) for obs in eval_observations]
            y_pred = [float(v) for v in forecast[sensor_id]]
            score_value = metric.compute(y_true, y_pred)
            score_values.append(score_value)
            db.add(Score(
                submission_id=submission.id,
                metric_id=metric.metric_id,
                value=score_value,
                details={
                    "sensor_id": sensor_id,
                    "eval_steps": eval_steps,
                    "scored_against": reference_key,
                },
            ))
    return score_values


async def _update_leaderboard(
    contest_id: UUID,
    user_id: UUID,
    submission_id: UUID,
    score_value: float,
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_factory() as db:
        result = await db.execute(
            select(LeaderboardEntry).where(
                LeaderboardEntry.contest_id == contest_id,
                LeaderboardEntry.user_id == user_id,
            )
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            entry = LeaderboardEntry(
                contest_id=contest_id,
                user_id=user_id,
                submission_id=submission_id,
                rank=0,
                score=score_value,
            )
            db.add(entry)
        elif score_value < entry.score:
            entry.submission_id = submission_id
            entry.score = score_value

        result = await db.execute(
            select(LeaderboardEntry)
            .where(LeaderboardEntry.contest_id == contest_id)
            .order_by(LeaderboardEntry.score.asc())
        )
        for rank, leaderboard_entry in enumerate(result.scalars(), start=1):
            leaderboard_entry.rank = rank
        await db.commit()


async def ensure_registered(
    db: AsyncSession, contest_id: UUID, user_id: UUID
) -> ContestRegistration:
    result = await db.execute(
        select(ContestRegistration).where(
            ContestRegistration.contest_id == contest_id,
            ContestRegistration.user_id == user_id,
            ContestRegistration.status == "REGISTERED",
        )
    )
    registration = result.scalar_one_or_none()
    if registration is None:
        raise RegistrationError("User is not registered for this contest")
    return registration


@router.post("/contests/{contest_id}/submissions", status_code=status.HTTP_201_CREATED)
async def create_submission(
    contest_id: str,
    request: CreateSubmissionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contest = await get_contest_or_raise(db, contest_id)
    if contest.status != "ACTIVE":
        raise ContestStateError("Contest is not active")
    await ensure_registered(db, contest.id, current_user.id)

    # Submissions are only accepted after the evaluation phase is complete.
    end_of_evaluation = as_utc(contest.end_of_observation) + timedelta(
        seconds=contest.prediction_horizon_seconds
    )
    if datetime.now(timezone.utc) < end_of_evaluation:
        raise ContestStateError(
            "Submissions are not yet accepted — the evaluation phase has not ended. "
            f"Submissions open at {end_of_evaluation.isoformat()}"
        )

    task_result = await db.execute(
        select(Task).where(
            Task.contest_id == contest.id,
            Task.task_type == request.task_id.upper(),
        )
    )
    if task_result.scalars().first() is None:
        raise SubmissionError(f"Task '{request.task_id}' does not belong to contest '{contest_id}'")

    submission = Submission(
        contest_id=contest.id,
        user_id=current_user.id,
        task_id=request.task_id,
        payload=request.payload,
        status="PENDING",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    asyncio.create_task(_score_submission(submission.id, get_session_factory()))
    return submission_response(submission)


@router.get("/contests/{contest_id}/submissions")
async def list_submissions(
    contest_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contest = await get_contest_or_raise(db, contest_id)
    query = select(Submission).where(Submission.contest_id == contest.id)
    if current_user.role == "ORGANIZER":
        if contest.created_by != current_user.id:
            raise InsufficientPermissionsError("Submission access denied")
    elif current_user.role != "ADMINISTRATOR":
        query = query.where(Submission.user_id == current_user.id)
    result = await db.execute(query)
    return {
        "submissions": [
            submission_summary(submission) for submission in result.scalars()
        ]
    }


@router.get("/submissions/{submission_id}")
async def get_submission(
    submission_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    submission_uuid = parse_uuid(
        submission_id,
        SubmissionError,
        f"Submission '{submission_id}' does not exist",
    )
    result = await db.execute(select(Submission).where(Submission.id == submission_uuid))
    submission = result.scalar_one_or_none()
    if submission is None:
        raise SubmissionError(f"Submission '{submission_id}' does not exist")
    if current_user.role == "ORGANIZER":
        result = await db.execute(
            select(Contest).where(Contest.id == submission.contest_id)
        )
        contest = result.scalar_one()
        if contest.created_by != current_user.id:
            raise InsufficientPermissionsError("Submission access denied")
    elif current_user.role != "ADMINISTRATOR" and submission.user_id != current_user.id:
        raise InsufficientPermissionsError("Submission access denied")
    return submission_response(submission)


@router.get("/submissions/{submission_id}/scores")
async def get_submission_scores(
    submission_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    submission_uuid = parse_uuid(
        submission_id,
        SubmissionError,
        f"Submission '{submission_id}' does not exist",
    )
    result = await db.execute(select(Submission).where(Submission.id == submission_uuid))
    submission = result.scalar_one_or_none()
    if submission is None:
        raise SubmissionError(f"Submission '{submission_id}' does not exist")
    if current_user.role == "ORGANIZER":
        result = await db.execute(
            select(Contest).where(Contest.id == submission.contest_id)
        )
        contest = result.scalar_one()
        if contest.created_by != current_user.id:
            raise InsufficientPermissionsError("Submission access denied")
    elif current_user.role != "ADMINISTRATOR" and submission.user_id != current_user.id:
        raise InsufficientPermissionsError("Submission access denied")

    result = await db.execute(select(Score).where(Score.submission_id == submission.id))
    return {
        "submission_id": str(submission.id),
        "scores": [
            {
                "score_id": str(score.id),
                "metric_id": score.metric_id,
                "value": score.value,
                "details": score.details,
                "computed_at": score.computed_at.isoformat(),
            }
            for score in result.scalars()
        ],
    }
