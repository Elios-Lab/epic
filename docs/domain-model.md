# EPIC Domain Model

This document explains the persistent entities of EPIC, their relationships, and the design rules behind the schema. It deliberately does not list every column: the authoritative field definitions are the SQLAlchemy models in `epic_core/db/models.py`, the API-facing shapes are the Pydantic models in `epic_api/schemas.py` (rendered live in the OpenAPI documentation), and the migration history is in `alembic/versions/`. What prose adds — and what this document contains — is the *why*: what each entity is for, how they relate, and the invariants the schema protects.

---

## The Entities

Eleven entities make a competition run end to end.

**User** is any account on the platform, carrying a role (`ADMINISTRATOR`, `ORGANIZER`, `PARTICIPANT`) and a status (`ACTIVE`, `SUSPENDED`, `DELETED` — deletion is a soft delete, preserving referential integrity for past contests and submissions). **OrganizerRequest** and **Invitation** support the two account-creation workflows: the former is an organizer's self-registration awaiting admin review, the latter a one-time, expiring, contest-scoped token sent by email to a prospective participant. Both record the resulting `user_id` once consumed, so the provenance of every account is auditable.

**Contest** is the central aggregate: it owns the simulation configuration (twin id, sensor configs, fault schedule, initial conditions, sampling rate), the schedule including the two-phase boundaries (`end_of_observation`, `prediction_horizon_seconds`), the lifecycle status, visibility, and ownership (`created_by`). **Task** declares what participants must produce for a contest — a type matched against the `TaskEvaluator` registry, metric ids, a weight, and a free-form configuration dictionary owned by the task type. **ContestRegistration** links a user to a contest with a status (`REGISTERED`, `WITHDRAWN`, `BANNED`).

**SimulationSession** is the runtime counterpart of a contest — exactly one per contest — recording the twin, sampling rate, optional random seed, engine status (`CREATED`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`), and timestamps. **SensorObservation** is what the engine persists during the evaluation phase: per step, the corrupted `sensors` readings, the clean `ground_truth` values, and the fault `labels`, keyed by a per-session `sequence_id`.

**Submission** holds a participant's prediction payload and its evaluation status (`PENDING`, `EVALUATED`, `FAILED`, with error details in its metadata). **Score** stores one metric result per sensor per submission, with a `details` dictionary recording the evaluation context (which sensor, how many steps, which reference signal). **LeaderboardEntry** keeps each participant's best submission per contest with its composite score and rank.

Digital twin and sensor metadata are deliberately *not* persisted: they are served live from the plugin registries, so the database never holds anything that could go stale when a plugin is updated.

---

## Relationships

```text
User
 ├── ContestRegistration
 ├── Submission
 └── Invitation (as invited_by)

OrganizerRequest
 └── (approved by User → creates User)

Contest
 ├── ContestRegistration
 ├── Task
 ├── Submission
 ├── LeaderboardEntry
 ├── Invitation
 └── SimulationSession (1:1)

SimulationSession
 └── SensorObservation

Submission
 └── Score
```

Deleting a contest cascades over everything it owns — tasks, registrations, invitations, submissions, scores, leaderboard entries, the session, and its observations — and is only permitted outside the ACTIVE state.

---

## Design Rules

**No executable logic in the database.** The database holds purely descriptive data — identifiers, configuration, observations, submissions, scores. The behavior those records refer to (twin physics, sensor pipelines, fault effects, evaluators) always lives in code, loaded through the plugin registries. This is what keeps the schema domain-independent: a new twin or task type changes no table.

**JSON where extensibility lives.** `sensor_configs`, `fault_schedule`, `initial_conditions`, `configuration`, `payload`, `details`, `labels`, and the metadata columns are JSON on purpose: their internal shape belongs to plugins and task types, not to the schema. On PostgreSQL these map to `JSONB`. Everything with a fixed, queryable meaning — statuses, timestamps, foreign keys, scores — is a real column.

**Data visibility is structural.** Every evaluation-phase observation carries three categories of data with different audiences: `sensors` (the corrupted readings participants saw or would have seen), `ground_truth` (clean latent values, server-only, used for scoring), and `labels` (fault metadata, server-only, used for anomaly-detection scoring). No participant-facing endpoint ever returns `ground_truth` or `labels`; the separation is enforced by the response models, not by convention.

**Uniqueness protects the invariants.** Usernames, emails, and contest names are unique; `(user_id, contest_id)` is unique on registrations (one registration per user per contest) and on leaderboard entries (one ranking row per participant); `contest_id` is unique on sessions (one session per contest, the anchor for resume-after-pause). Invitation tokens are unique and single-use by construction.

**Indexes follow the access paths.** Lookups by status (users, contests, sessions), by foreign key (registrations, submissions, scores, observations by session), and by the engine's hot path (`sensor_observations.sequence_id` for resume and scoring) are indexed; the models file is the authoritative list.

**Reproducibility is a schema concern.** Every session must remain reconstructible from what is stored: the twin identifier, the random seed, and the full simulation, contest, and scoring configurations are all persisted, so past contests and submissions can be audited and reproduced even after the platform has evolved.

---

## Future Extensions

Entities anticipated but deliberately not yet modelled: `Team` and `TeamMembership` for team-based contests, public/private leaderboard splits, baseline models and model artifacts, evaluation jobs (if scoring moves out of process), and a persistent audit log. Multi-twin contests with version pinning (a junction table in place of the contest's single `twin_id`) are similarly deferred. Each of these is additive — the test applied before accepting any of them is that existing tables and migrations survive unchanged.
