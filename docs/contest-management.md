# Contest Management Framework

> Related: [Domain Model](domain-model.md) — canonical entity definitions · [API Specification](api-specification.md) — REST endpoints · [Scoring](scoring.md) — metrics and leaderboards

The Contest Management Framework is responsible for creating, managing and evaluating machine learning competitions within EPIC. A contest is the primary organizational unit of the platform: participants never interact directly with digital twins, they interact with contests that use a digital twin as a problem generator.

The framework is designed to run multiple simultaneous contests with distinct participant groups, different tasks and scoring policies, different digital twins, and different difficulty levels, while keeping evaluation fully automatic and competitions reproducible. Crucially, it must remain independent from any particular digital twin — a contest references a twin only by its registered identifier.

---

# Core Concepts

The contest system is built around seven entities: `User`, `Contest`, `ContestRegistration`, `Task`, `Submission`, `Score`, and `LeaderboardEntry`. A contest carries the simulation configuration and the schedule; tasks define what participants must produce and how it is scored; registrations link users to contests; submissions hold the predictions; scores and leaderboard entries hold the evaluation results. See [Domain Model](domain-model.md) for the canonical entity definitions and the full relational structure.

A contest itself bundles metadata (name, description, visibility), the schedule (start, end, and the two-phase boundaries), the simulation configuration (twin, sensor configs, fault schedule, initial conditions, sampling rate), and ownership information. Tasks and scoring configuration are linked entities managed separately.

---

# Contest Lifecycle

Every contest follows a linear lifecycle:

```text
DRAFT → SCHEDULED → ACTIVE → CLOSED → ARCHIVED
```

Transitions must follow this order — skipping states (for example `DRAFT → ACTIVE`) is not allowed, and any attempt to perform an invalid transition returns `409 Conflict` with error code `CONTEST_STATE_ERROR`. The transitions from `DRAFT` to `SCHEDULED`, from `SCHEDULED` to `ACTIVE`, and from `ACTIVE` to `CLOSED` can be performed by the contest's own organizer or by an administrator; the final transition from `CLOSED` to `ARCHIVED` is reserved to administrators.

In the **DRAFT** state the contest is being configured. It is visible only to its creator and to administrators, and submissions are disabled. Once published to **SCHEDULED**, the contest becomes visible and participants may register, but submissions remain disabled and no simulation runs yet.

The **ACTIVE** state is where the actual competition happens, and it spans three sub-phases defined by `end_of_observation` and `prediction_horizon_seconds`. During the *observation* sub-phase, from `start_date` to `end_of_observation`, the simulation runs and participants receive live sensor readings over the WebSocket stream. During the *evaluation* sub-phase, which lasts `prediction_horizon_seconds` from the end of observation, the simulation continues running but the stream is closed; the ground truth produced in this window is recorded privately and hidden from participants. Finally, in the *submission* sub-phase, which opens when the evaluation window ends and lasts until `end_date`, participants submit their forecasts, submissions are scored automatically, and the leaderboard updates. The platform creates and starts the contest's simulation session automatically on activation; organizers and administrators can pause and resume the session, participants cannot.

When the contest is **CLOSED**, the simulation session is stopped and marked COMPLETED, new submissions are rejected, scores become final, and participants can no longer connect to the WebSocket stream. The **ARCHIVED** state preserves the contest read-only for historical purposes.

---

# Visibility

A contest declares one of three visibility modes: `PUBLIC`, `PRIVATE`, or `INVITATION_ONLY`. Public contests are listed for every authenticated user; private and invitation-only contests restrict who can discover and join them.

---

# Tasks

A contest may contain one or more tasks, evaluated independently. A task is defined by its type, the metrics used to score it, a weight for composite scoring, and a free-form `configuration` dictionary whose content depends on the task type (for forecasting it carries `eval_steps` and `score_against`).

The currently implemented task type is `FORECASTING`. Anomaly detection, fault classification, and remaining-useful-life estimation are planned task types; the entity model already accommodates them, since tasks carry their own type, metrics, and configuration.

---

# Templates

Predefined contest templates are available for all five built-in twins and are exposed via `GET /api/v1/templates`. A template is a complete, working configuration for a specific twin — sensor configs with realistic noise levels, a fault schedule, initial conditions, and a sampling rate — that an organizer can instantiate and then override parameter by parameter, instead of configuring a simulation from scratch. User-defined reusable templates, saved and shared between organizers, are a planned extension.

---

# Users, Roles, and Permissions

Three roles exist. The **ADMINISTRATOR** has full control over all contests and all users — everything an organizer can do, platform-wide, plus user management and archival. The **ORGANIZER** creates contests and manages their own through the full lifecycle: they can extend deadlines, view every submission made to their contests, and pause or resume their simulation sessions, but they cannot touch other organizers' contests or manage users. The **PARTICIPANT** registers for contests in the SCHEDULED or ACTIVE state, connects to the WebSocket stream to collect data during the observation phase, submits forecasts once the submission window opens, and views their own scores and ranking.

How accounts are created differs by role: organizers self-register through a request queue reviewed by an administrator, while participants are invited per-contest by the organizer. See [Authentication](authentication.md) for the complete registration workflows.

---

# Registrations

A registration links a user to a contest, with statuses `REGISTERED`, `WITHDRAWN`, and `BANNED`. The pair `(user_id, contest_id)` is unique — a user registers at most once per contest — and only users with an active registration may connect to the data stream or submit solutions.

---

# Submissions

Submissions are the primary evaluation mechanism. A submission records who submitted what for which task and when: it carries the contest, the user, the task identifier, a server-assigned timestamp, the prediction payload (for forecasting, one list of values per sensor under the `forecast` key), a status that progresses from `PENDING` to `EVALUATED` or `FAILED`, and an optional metadata dictionary where the platform records error details when validation or scoring fails.

Temporal integrity is enforced by the two-phase structure rather than by trust: the server only accepts submissions after `end_of_observation + prediction_horizon_seconds`, when the full ground truth for the evaluation window already exists, and forecasts must cover exactly `eval_steps` values per sensor. This makes retroactive "predictions" structurally impossible. See [Scoring](scoring.md) for the full explanation.

Every submission then follows the same pipeline: validation of the contest state, the registration, the payload format, and the task compatibility; scoring against the recorded ground truth; storage of one `Score` row per metric per sensor; and finally a leaderboard update. Invalid submissions are rejected with an explanatory error in their metadata.

Submission *policies* — how many submissions a participant may make and which one counts — are a configuration axis of the framework. The current implementation accepts unlimited submissions and ranks each participant by their best score; daily limits and latest-submission ranking are planned policy options.

---

# Leaderboards

Each contest owns one leaderboard, generated automatically as submissions are evaluated. An entry records the participant, their best submission, its composite score, and the resulting rank; ranks are recomputed across the whole contest on every accepted score, so the leaderboard is always current.

Ranking supports three conceptual modes: *best score*, where each participant's strongest submission counts; *latest submission*, where the most recent valid one counts; and *multi-metric*, where several metric values are combined into a single ranking score through configured weights (for example seventy percent forecasting quality, thirty percent anomaly detection). The current implementation provides best-score ranking on the value returned by the task's evaluator, honouring the metric's declared direction — lowest-first for minimized metrics like MAE, highest-first for maximized ones like F1. The leaderboard visibility modes `PUBLIC`, `PARTICIPANT_ONLY`, and `ADMIN_ONLY`, as well as Kaggle-style public/private leaderboard splits, are part of the roadmap.

---

# Deadline Management

Organizers (for their own contests) and administrators can modify the contest schedule — including the end date — even after publication, without recreating the contest. The typical use case is a deadline extension while a contest is running: the simulation engine picks up end-date changes dynamically.

---

# Auditability

The system keeps a durable record of contest creation and updates, registrations, submissions, and score changes, each carrying server-side timestamps. For educational and research use this matters twice over: instructors can reconstruct exactly what every participant did and when, and researchers can verify that reported results correspond to what the platform actually recorded.

---

# Future Extensions

Several extensions are anticipated and deliberately kept out of the current scope: team-based contests, multi-stage competitions, hidden test sets, private leaderboards, peer-reviewed solutions, and automatic report generation. None of them require changes to the entity model beyond additive ones, which is the test applied before accepting any of these features into the roadmap.

---

# Long-Term Goal

The Contest Management Framework should allow instructors and researchers to create new competitions without writing code. A contest should be definable purely through configuration — twin, sensors, faults, schedule, tasks, metrics — while digital twins provide the underlying simulation environment.
