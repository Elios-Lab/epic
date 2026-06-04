"""Submission endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from epic_api.dependencies import get_current_user
from epic_core.db.models import (
    Contest,
    ContestRegistration,
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
        submission.status = "EVALUATED"
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
