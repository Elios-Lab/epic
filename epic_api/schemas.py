"""Pydantic response models for the EPIC API.

These models serve two purposes: they make the generated OpenAPI schema a
complete, accurate contract (response shapes included), and they prevent the
hand-written docs from drifting — the wire format is locked in code.

Models that carry plugin-provided metadata (twins, sensors, faults,
templates) declare the minimum contract fields and allow extras, so a
plugin adding metadata keys never has data silently dropped.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# ── Auth ──────────────────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int | None = None


class MeResponse(BaseModel):
    user_id: str
    username: str
    email: str
    role: str
    is_active: bool


# ── Users ─────────────────────────────────────────────────────────────────────


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    role: str
    status: str
    is_active: bool  # backward-compat shim
    created_at: datetime | None = None


class UserListResponse(BaseModel):
    total: int
    users: list[UserResponse]


# ── Organizer requests ────────────────────────────────────────────────────────


class OrganizerRequestResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone_number: str | None = None
    status: str
    reviewed_at: datetime | None = None
    user_id: str | None = None
    created_at: datetime | None = None


class OrganizerRequestListResponse(BaseModel):
    total: int
    requests: list[OrganizerRequestResponse]


# ── Invitations ───────────────────────────────────────────────────────────────


class InvitationSummary(BaseModel):
    id: str
    email: str
    contest_id: str
    expires_at: datetime
    used: bool
    created_at: datetime | None = None


class CreateInvitationsResponse(BaseModel):
    created: int
    invitations: list[InvitationSummary]


class InvitationDetails(BaseModel):
    email: str
    contest_id: str
    contest_name: str | None = None
    expires_at: datetime
    valid: bool


class InvitedUserResponse(BaseModel):
    id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str
    status: str
    created_at: datetime | None = None


class AcceptInvitationResponse(BaseModel):
    user: InvitedUserResponse
    access_token: str
    token_type: str


# ── Contests and tasks ────────────────────────────────────────────────────────


class TaskResponse(BaseModel):
    task_id: str
    task_type: str
    name: str
    weight: float
    configuration: dict[str, Any]


class ContestResponse(BaseModel):
    contest_id: str
    name: str
    description: str | None = None
    status: str
    visibility: str
    twin_id: str
    sensor_configs: list[dict[str, Any]]
    fault_schedule: list[dict[str, Any]]
    initial_conditions: dict[str, Any] | None = None
    sampling_rate_hz: float
    start_date: datetime | None = None
    end_date: datetime | None = None
    end_of_observation: datetime | None = None
    prediction_horizon_seconds: float | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    tasks: list[TaskResponse]


class ContestListResponse(BaseModel):
    total: int
    contests: list[ContestResponse]


# ── Registrations ─────────────────────────────────────────────────────────────


class RegistrationResponse(BaseModel):
    registration_id: str
    contest_id: str
    user_id: str
    registered_at: datetime
    status: str


class RegistrationListResponse(BaseModel):
    registrations: list[RegistrationResponse]


# ── Submissions and scores ────────────────────────────────────────────────────


class SubmissionSummary(BaseModel):
    submission_id: str
    user_id: str
    task_id: str
    submitted_at: datetime
    status: str


class SubmissionResponse(SubmissionSummary):
    contest_id: str
    payload: dict[str, Any]
    submission_metadata: dict[str, Any] | None = None


class SubmissionListResponse(BaseModel):
    submissions: list[SubmissionSummary]


class ScoreResponse(BaseModel):
    score_id: str
    metric_id: str
    value: float
    details: dict[str, Any] | None = None
    computed_at: datetime


class SubmissionScoresResponse(BaseModel):
    submission_id: str
    scores: list[ScoreResponse]


# ── Leaderboard ───────────────────────────────────────────────────────────────


class LeaderboardEntryResponse(BaseModel):
    rank: int
    user_id: str
    username: str
    submission_id: str
    score: float
    updated_at: datetime


class LeaderboardResponse(BaseModel):
    contest_id: str
    entries: list[LeaderboardEntryResponse]


# ── Sessions ──────────────────────────────────────────────────────────────────


class SessionResponse(BaseModel):
    session_id: str
    contest_id: str
    twin_id: str
    sampling_rate_hz: float
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None


# ── Plugin metadata (open contracts: extras are allowed and preserved) ────────


class TwinMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    twin_id: str
    name: str
    version: str
    description: str


class SensorMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    sensor_id: str
    name: str
    unit: str
    measured_quantity: str
    version: str
    description: str


class FaultMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    fault_id: str
    name: str
    version: str
    description: str


class TwinListResponse(BaseModel):
    twins: list[TwinMetadata]


class TwinSensorsResponse(BaseModel):
    twin_id: str
    sensors: list[SensorMetadata]


class TwinFaultsResponse(BaseModel):
    twin_id: str
    faults: list[FaultMetadata]


# ── Catalog ───────────────────────────────────────────────────────────────────


class CatalogSummary(BaseModel):
    twin_id: str
    name: str
    description: str
    version: str


class CatalogListResponse(BaseModel):
    twins: list[CatalogSummary]


class TemplateSummary(BaseModel):
    template_id: str
    name: str
    description: str
    twin_id: str
    sampling_rate_hz: float
    task_type: str


class TemplateDetail(TemplateSummary):
    model_config = ConfigDict(extra="allow")

    sensor_configs: list[dict[str, Any]]
    fault_schedule: list[dict[str, Any]]
    initial_conditions: dict[str, Any] | None = None


class CatalogProfileResponse(BaseModel):
    metadata: TwinMetadata
    supported_quantities: list[str]
    faults: list[FaultMetadata]
    sensors: list[SensorMetadata]
    templates: list[TemplateSummary]


class TemplateListResponse(BaseModel):
    templates: list[TemplateSummary]
