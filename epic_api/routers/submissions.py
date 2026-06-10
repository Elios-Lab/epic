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
from epic_api.dependencies import get_current_user, get_notification_service
from epic_api.utils import get_contest_or_raise, parse_uuid
from epic_api.schemas import (
    SubmissionListResponse,
    SubmissionResponse,
    SubmissionScoresResponse,
)
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
from epic_core.notifications import NotificationService, SubmissionReceived
from epic_core.exceptions import (
    ContestStateError,
    EvaluationPendingError,
    InsufficientPermissionsError,
    PluginNotFoundError,
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
            await _fail_submission(db, submission, "Task not found for this contest")
            return

        try:
            evaluator = registry_module.task_evaluator_registry.get(task.task_type)
        except PluginNotFoundError:
            await _fail_submission(
                db,
                submission,
                f"No evaluator registered for task type '{task.task_type}'",
            )
            return

        metric_ids = task.metric_ids or evaluator.default_metric_ids
        try:
            metrics = [
                registry_module.metric_registry.get(metric_id)
                for metric_id in metric_ids
            ]
        except PluginNotFoundError as exc:
            await _fail_submission(db, submission, str(exc))
            return

        observations = await _load_evaluation_observations(
            db, contest.id, evaluator.observation_limit(task.configuration)
        )

        try:
            evaluation = evaluator.evaluate(
                submission.payload, task.configuration, observations, metrics
            )
        except EvaluationPendingError:
            submission.status = "PENDING"
            await db.commit()
            return
        except SubmissionError as exc:
            await _fail_submission(db, submission, str(exc))
            return

        for score in evaluation.scores:
            db.add(Score(
                submission_id=submission.id,
                metric_id=score.metric_id,
                value=score.value,
                details=score.details,
            ))
        submission.status = "EVALUATED"
        await db.commit()

        if evaluation.ranking_value is not None:
            await _update_leaderboard(
                submission.contest_id,
                submission.user_id,
                submission.id,
                evaluation.ranking_value,
                evaluation.ranking_direction,
                db_factory,
            )


async def _fail_submission(db, submission: Submission, error: str) -> None:
    submission.status = "FAILED"
    submission.submission_metadata = {
        **(submission.submission_metadata or {}),
        "error": error,
    }
    await db.commit()


async def _load_evaluation_observations(
    db, contest_id: UUID, limit: int | None = None
) -> list[dict]:
    """Load evaluation-phase observations as plain dicts for the evaluator.

    The limit comes from the evaluator's observation_limit() and bounds the
    query so scoring cost is proportional to the evaluation window, not to
    the full contest history.
    """
    query = (
        select(SensorObservation)
        .join(SimulationSession, SensorObservation.session_id == SimulationSession.id)
        .where(SimulationSession.contest_id == contest_id)
        .order_by(SensorObservation.sequence_id.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    obs_result = await db.execute(query)
    return [
        {
            "sequence_id": obs.sequence_id,
            "sensors": obs.sensors,
            "ground_truth": obs.ground_truth,
            "labels": obs.labels,
        }
        for obs in obs_result.scalars()
    ]


async def _update_leaderboard(
    contest_id: UUID,
    user_id: UUID,
    submission_id: UUID,
    score_value: float,
    direction: str,
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Keep each participant's best score, honouring the metric direction."""
    minimize = direction != "maximize"
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
        elif (score_value < entry.score) if minimize else (score_value > entry.score):
            entry.submission_id = submission_id
            entry.score = score_value

        order = (
            LeaderboardEntry.score.asc() if minimize else LeaderboardEntry.score.desc()
        )
        result = await db.execute(
            select(LeaderboardEntry)
            .where(LeaderboardEntry.contest_id == contest_id)
            .order_by(order)
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


@router.post(
    "/contests/{contest_id}/submissions",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmissionResponse,
)
async def create_submission(
    contest_id: str,
    request: CreateSubmissionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    notifications: NotificationService = Depends(get_notification_service),
):
    contest = await get_contest_or_raise(db, contest_id)
    if contest.status != "ACTIVE":
        raise ContestStateError("Contest is not active")
    await ensure_registered(db, contest.id, current_user.id)

    # Submissions require a two-phase contest: without an evaluation window
    # there is no ground truth to score against.
    if (
        contest.end_of_observation is None
        or contest.prediction_horizon_seconds is None
    ):
        raise ContestStateError(
            "Contest does not accept submissions — it is not configured as a "
            "two-phase contest (end_of_observation and "
            "prediction_horizon_seconds are required)"
        )

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

    # Notify the contest owner.
    if contest.created_by is not None:
        owner_result = await db.execute(select(User).where(User.id == contest.created_by))
        owner = owner_result.scalar_one_or_none()
        if owner is not None:
            await notifications.notify(SubmissionReceived(
                to_email=owner.email,
                contest_name=contest.name,
                participant_username=current_user.username,
                submission_id=str(submission.id),
            ))

    asyncio.create_task(_score_submission(submission.id, get_session_factory()))
    return submission_response(submission)


@router.get("/contests/{contest_id}/submissions", response_model=SubmissionListResponse)
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


@router.get("/submissions/{submission_id}", response_model=SubmissionResponse)
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


@router.get("/submissions/{submission_id}/scores", response_model=SubmissionScoresResponse)
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
