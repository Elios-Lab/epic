"""Submission endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import epic_core.registry as registry_module
from epic_api.dependencies import get_current_user
from epic_core.db.models import (
    Contest,
    ContestRegistration,
    LeaderboardEntry,
    Score,
    SensorObservation,
    SimulationSession,
    Submission,
    User,
)
from epic_core.db.session import get_db, get_session_factory
from epic_core.exceptions import (
    ContestNotFoundError,
    ContestStateError,
    InsufficientPermissionsError,
    RegistrationError,
    SubmissionError,
)

router = APIRouter(tags=["submissions"])


class CreateSubmissionRequest(BaseModel):
    task_id: str
    prediction_from_sequence: int
    payload: dict


def parse_uuid(value: str, error_cls, message: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise error_cls(message) from exc


def submission_summary(submission: Submission) -> dict:
    return {
        "submission_id": str(submission.id),
        "user_id": str(submission.user_id),
        "task_id": submission.task_id,
        "prediction_from_sequence": submission.prediction_from_sequence,
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
        if contest.task_type != "FORECASTING":
            submission.status = "EVALUATED"
            await db.commit()
            return

        horizons = contest.forecast_horizons or [1, 5, 10]
        observations: dict[int, SensorObservation] = {}
        for horizon in horizons:
            result = await db.execute(
                select(SensorObservation)
                .join(
                    SimulationSession,
                    SensorObservation.session_id == SimulationSession.id,
                )
                .where(
                    SimulationSession.contest_id == contest.id,
                    SensorObservation.sequence_id
                    == submission.prediction_from_sequence + horizon,
                )
            )
            observation = result.scalar_one_or_none()
            if observation is None:
                submission.status = "PENDING"
                await db.commit()
                return
            observations[horizon] = observation

        try:
            forecast = submission.payload["forecast"]
            predictions_by_sensor: dict[str, dict[int, float]] = {}
            details_by_sensor: dict[str, dict[str, dict[str, float]]] = {}
            for horizon in horizons:
                horizon_predictions = forecast[f"horizon_{horizon}"]
                if not isinstance(horizon_predictions, dict):
                    raise TypeError(f"horizon_{horizon} must be a prediction dict")
                for sensor_id, predicted_value in horizon_predictions.items():
                    true_value = observations[horizon].sensors[sensor_id]
                    predicted_float = float(predicted_value)
                    true_float = float(true_value)
                    predictions_by_sensor.setdefault(sensor_id, {})[horizon] = (
                        predicted_float
                    )
                    details_by_sensor.setdefault(sensor_id, {})[
                        f"horizon_{horizon}"
                    ] = {
                        "y_true": true_float,
                        "y_pred": predicted_float,
                        "absolute_error": abs(true_float - predicted_float),
                    }
        except (KeyError, TypeError, ValueError) as exc:
            submission.status = "FAILED"
            submission.submission_metadata = {
                **(submission.submission_metadata or {}),
                "error": str(exc),
            }
            await db.commit()
            return

        metric = registry_module.metric_registry.get("mae")
        score_values: list[float] = []
        for sensor_id, horizon_predictions in predictions_by_sensor.items():
            sensor_horizons = sorted(horizon_predictions)
            y_true = [
                float(observations[horizon].sensors[sensor_id])
                for horizon in sensor_horizons
            ]
            y_pred = [horizon_predictions[horizon] for horizon in sensor_horizons]
            score_value = metric.compute(y_true, y_pred)
            score_values.append(score_value)
            db.add(
                Score(
                    submission_id=submission.id,
                    metric_id=metric.metric_id,
                    value=score_value,
                    details={
                        "sensor_id": sensor_id,
                        "horizons": details_by_sensor[sensor_id],
                    },
                )
            )
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


async def ensure_observation_exists(
    db: AsyncSession, contest_id: UUID, sequence_id: int
) -> None:
    result = await db.execute(
        select(SensorObservation)
        .join(
            SimulationSession,
            SensorObservation.session_id == SimulationSession.id,
        )
        .where(
            SimulationSession.contest_id == contest_id,
            SensorObservation.sequence_id == sequence_id,
        )
    )
    observation = result.scalar_one_or_none()
    if observation is None or as_utc(observation.timestamp) > datetime.now(timezone.utc):
        raise SubmissionError(
            "prediction_from_sequence references an observation that does not exist"
        )


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
    await ensure_observation_exists(db, contest.id, request.prediction_from_sequence)

    submission = Submission(
        contest_id=contest.id,
        user_id=current_user.id,
        task_id=request.task_id,
        prediction_from_sequence=request.prediction_from_sequence,
        payload=request.payload,
        status="PENDING",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    response = {
        "submission_id": str(submission.id),
        "contest_id": str(submission.contest_id),
        "user_id": str(submission.user_id),
        "task_id": submission.task_id,
        "prediction_from_sequence": submission.prediction_from_sequence,
        "submitted_at": submission.submitted_at.isoformat(),
        "status": submission.status,
    }
    asyncio.create_task(_score_submission(submission.id, get_session_factory()))
    return response


@router.get("/contests/{contest_id}/submissions")
async def list_submissions(
    contest_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contest = await get_contest_or_raise(db, contest_id)
    query = select(Submission).where(Submission.contest_id == contest.id)
    if current_user.role == "ORGANIZER":
        if contest.created_by != current_user.username:
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
        if contest.created_by != current_user.username:
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
        if contest.created_by != current_user.username:
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
