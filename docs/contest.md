# Contests

A contest is the primary organizational unit of EPIC: participants never interact directly with digital twins, they interact with contests that use a digital twin as a problem generator. This document covers both sides of that coin: first how the contest framework works (lifecycle, roles, submissions, leaderboards), then how an organizer authors a contest through configuration alone.

The framework is designed to run multiple simultaneous contests with distinct participant groups, different tasks and scoring policies, different digital twins, and different difficulty levels, while keeping evaluation fully automatic and competitions reproducible. Crucially, it remains independent from any particular digital twin, a contest references a twin only by its registered identifier.

---

## How Contests Work

Every contest follows a linear lifecycle:

```text
DRAFT → SCHEDULED → ACTIVE → CLOSED → ARCHIVED
```

Transitions must follow this order, skipping states (for example `DRAFT → ACTIVE`) is not allowed, and any attempt to perform an invalid transition returns `409 Conflict` with error code `CONTEST_STATE_ERROR`. The transitions from `DRAFT` to `SCHEDULED`, from `SCHEDULED` to `ACTIVE`, and from `ACTIVE` to `CLOSED` can be performed by the contest's own organizer or by an administrator; the final transition from `CLOSED` to `ARCHIVED` is reserved to administrators.

In the **DRAFT** state the contest is being configured. It is visible only to its creator and to administrators, and submissions are disabled. Once published to **SCHEDULED**, the contest becomes visible and participants may register, but submissions remain disabled and no simulation runs yet.

The **ACTIVE** state is where the actual competition happens, and it spans three sub-phases defined by `end_of_observation` and `prediction_horizon_seconds`. During the *observation* sub-phase, from `start_date` to `end_of_observation`, the simulation runs and participants receive live sensor readings over the WebSocket stream. During the *evaluation* sub-phase, which lasts `prediction_horizon_seconds` from the end of observation, the simulation continues running but the stream is closed; the ground truth produced in this window is recorded privately and hidden from participants. Finally, in the *submission* sub-phase, which opens when the evaluation window ends and lasts until `end_date`, participants submit their forecasts, submissions are scored automatically, and the leaderboard updates. The platform creates and starts the contest's simulation session automatically on activation; organizers and administrators can pause and resume the session, participants cannot.

When the contest is **CLOSED**, the simulation session is stopped and marked COMPLETED, new submissions are rejected, scores become final, and participants can no longer connect to the WebSocket stream. The **ARCHIVED** state preserves the contest read-only for historical purposes.

### Visibility

A contest declares one of three visibility modes: `PUBLIC`, `PRIVATE`, or `INVITATION_ONLY`. Public contests are listed for every authenticated user; private and invitation-only contests restrict who can discover and join them.

### Tasks

A contest may contain one or more tasks, evaluated independently. A task is defined by its type, the metrics used to score it, a weight for composite scoring, and a free-form `configuration` dictionary whose content depends on the task type (for forecasting it carries `eval_steps` and `score_against`).

Task types are plugins: any type with a registered `TaskEvaluator` is accepted at contest creation and scored automatically — see [Scoring](scoring.md). The built-in task type is `FORECASTING`; anomaly detection, fault classification, and remaining-useful-life estimation are planned, each arriving as an evaluator plugin rather than a platform change.

### Users, Roles, and Permissions

Three roles exist. The **ADMINISTRATOR** has full control over all contests and all users — everything an organizer can do, platform-wide, plus user management and archival. The **ORGANIZER** creates contests and manages their own through the full lifecycle: they can extend deadlines, view every submission made to their contests, and pause or resume their simulation sessions, but they cannot touch other organizers' contests or manage users. The **PARTICIPANT** registers for contests in the SCHEDULED or ACTIVE state, connects to the WebSocket stream to collect data during the observation phase, submits forecasts once the submission window opens, and views their own scores and ranking.

How accounts are created differs by role: organizers self-register through a request queue reviewed by an administrator, while participants are invited per-contest by the organizer. See [Authentication](authentication.md) for the complete registration workflows.

### Registrations

A registration links a user to a contest, with statuses `REGISTERED`, `WITHDRAWN`, and `BANNED`. The pair `(user_id, contest_id)` is unique — a user registers at most once per contest — and only users with an active registration may connect to the data stream or submit solutions. Participants who join through an invitation link are registered automatically when their account is created.

### Submissions

Submissions are the primary evaluation mechanism. A submission records who submitted what for which task and when: it carries the contest, the user, the task identifier, a server-assigned timestamp, the prediction payload (for forecasting, one list of values per sensor under the `forecast` key), a status that progresses from `PENDING` to `EVALUATED` or `FAILED`, and an optional metadata dictionary where the platform records error details when validation or scoring fails.

Temporal integrity is enforced by the two-phase structure rather than by trust: the server only accepts submissions after `end_of_observation + prediction_horizon_seconds`, when the full ground truth for the evaluation window already exists, and forecasts must cover exactly `eval_steps` values per sensor. This makes retroactive "predictions" structurally impossible. See [Scoring](scoring.md) for the full explanation.

Every submission then follows the same pipeline: validation of the contest state, the registration, the payload format, and the task compatibility; scoring against the recorded ground truth; storage of one `Score` row per metric per sensor; and finally a leaderboard update. Invalid submissions are rejected with an explanatory error in their metadata.

Submission *policies* — how many submissions a participant may make and which one counts — are a configuration axis of the framework. The current implementation accepts unlimited submissions and ranks each participant by their best score; daily limits and latest-submission ranking are planned policy options.

### Leaderboards

Each contest owns one leaderboard, generated automatically as submissions are evaluated. An entry records the participant, their best submission, its composite score, and the resulting rank; ranks are recomputed across the whole contest on every accepted score, so the leaderboard is always current.

Ranking supports three conceptual modes: *best score*, where each participant's strongest submission counts; *latest submission*, where the most recent valid one counts; and *multi-metric*, where several metric values are combined into a single ranking score through configured weights (for example seventy percent forecasting quality, thirty percent anomaly detection). The current implementation provides best-score ranking on the value returned by the task's evaluator, honouring the metric's declared direction — lowest-first for minimized metrics like MAE, highest-first for maximized ones like F1. The leaderboard visibility modes `PUBLIC`, `PARTICIPANT_ONLY`, and `ADMIN_ONLY`, as well as Kaggle-style public/private leaderboard splits, are part of the roadmap.

### Deadline Management

Organizers (for their own contests) and administrators can modify the contest schedule — including the end date — even after publication, without recreating the contest. The typical use case is a deadline extension while a contest is running: the simulation engine picks up end-date changes dynamically.

### Notifications

The platform keeps the people behind a contest informed by email, through an event-based notification service (`epic_core/notifications.py`). Each notification is a typed event delivered to one recipient; the delivery mechanism is an injected adapter (SMTP in production, a no-op when mail is not configured), so the business logic never depends on a specific provider, and adding a notification means defining one event class and one template — the service interface never changes.

Administrators are notified when a new organizer registration request arrives and when an organizer creates a new contest. Organizers are notified when a participant registers for their contest, when an invitation they sent is accepted, and when a submission arrives. Both organizers and administrators are alerted for the operational events that would otherwise fail silently: a simulation session crashing, or a session being auto-paused by the restart recovery — the cases where someone needs to log in and press Resume. Participants receive their invitation links, and when a contest's evaluation window ends they are told that the submission window is open.

All notifications are fire-and-forget: a mail outage is logged but never blocks registration, submission intake, or the simulation loop. High-frequency events — submission notifications above all — are candidates for per-user digest preferences as contest sizes grow; the event-based design accommodates that without interface changes.

### Auditability

The system keeps a durable record of contest creation and updates, registrations, submissions, and score changes, each carrying server-side timestamps. For educational and research use this matters twice over: instructors can reconstruct exactly what every participant did and when, and researchers can verify that reported results correspond to what the platform actually recorded.

### Future Extensions

Several extensions are anticipated and deliberately kept out of the current scope: team-based contests, multi-stage competitions, hidden test sets, private leaderboards, peer-reviewed solutions, and automatic report generation. None of them require changes to the entity model beyond additive ones, which is the test applied before accepting any of these features into the roadmap.

---

## Part II — Authoring a Contest

One of the primary goals of EPIC is to allow instructors and researchers to create machine learning competitions without modifying the platform code. Contest creation is configuration-driven: an author defines a complete competition by choosing a digital twin, tuning the sensor pipeline parameters, scheduling faults (which ones, when they start and end, and how severe), setting the initial conditions, declaring the task with its scoring metrics, and choosing visibility — all without implementing a single new software component. The five built-in twins available for this configuration are described in the [Digital Twins](digital-twins.md) catalog.

Contests can be authored three ways: through the web interface (the organizer dashboard offers a template-driven creation form), by retrieving a template from `GET /api/v1/templates` and submitting it with overrides, or by building the full configuration by hand against `POST /api/v1/contests`. All three paths produce the same contest record; this section documents the configuration itself.

### Workflow

```text
Select Twin
      ↓
Configure Sensors (with parameter overrides)
      ↓
Configure Fault Schedule (fault_id, start_time, end_time, severity)
      ↓
Set Initial Conditions
      ↓
Set the Two-Phase Schedule
      ↓
Choose Task and Metrics
      ↓
Publish Contest
```

All configuration is stored directly on the contest record, so every contest explicitly carries its full simulation configuration — a prerequisite for reproducibility.

### Twin, Sensors, Faults, and Initial Conditions

A contest uses exactly one digital twin, referenced by id (`twin_id: mass_spring_damper`). For each sensor, the author specifies the `sensor_id` and optional parameter overrides for the measurement pipeline described in [Sensors](sensors.md):

```yaml
sensor_configs:
  - sensor_id: position
    noise_std: 0.005
  - sensor_id: velocity
    noise_std: 0.01
    drift_rate: 0.0005
  - sensor_id: temperature
    noise_std: 0.2
    p_outlier: 0.002
```

The platform validates at creation time that at least one sensor is configured and that each sensor is compatible with the selected twin (its `measured_quantity` must be among the twin's `supported_quantities()`).

The fault schedule declares which physical faults to inject and when, in seconds from simulation start; a `null` end time means the fault stays active until the contest ends, and severity is a value in `[0, 1]` scaling the fault's strength:

```yaml
fault_schedule:
  - fault_id: increased_damping
    start_time: 3600.0
    end_time: null
    severity: 0.3
  - fault_id: reduced_stiffness
    start_time: 7200.0
    end_time: 10800.0
    severity: 0.5
```

Each `fault_id` must be one of the faults the twin itself exposes — the catalog in [Digital Twins](digital-twins.md) lists them per twin — and this too is validated at creation time.

Initial conditions optionally override the twin's default starting state; unspecified fields keep their defaults:

```yaml
initial_conditions:
  position: 0.5
  velocity: 0.0
```

### The Two-Phase Schedule

Every contest uses the two-phase structure described in Part I. The author sets two fields beyond the start and end dates:

```yaml
end_of_observation: 2027-01-15T12:00:00Z   # observation phase ends, stream closes
prediction_horizon_seconds: 60.0            # length of the hidden evaluation window
```

The platform computes `eval_steps = round(prediction_horizon_seconds × sampling_rate_hz)`, the number of values participants must predict per sensor. `end_date` must fall after `end_of_observation + prediction_horizon_seconds`, leaving participants time to submit.

One optional field selects the scoring reference. With the recommended default, `score_against: ground_truth`, scores are computed against the noiseless latent-state values recorded by the engine, so a perfect physics model achieves a score of zero and measurement noise does not penalise it. With `score_against: sensors`, scores are computed against the noisy sensor readings instead; choose this only when forecasting the corrupted measurement is itself the point, as in a sensor-drift challenge.

### Task and Metrics

The `task_type` field (default `FORECASTING`) selects the contest's task; any type with a registered `TaskEvaluator` plugin is valid. `metric_ids` lists the scoring metrics (default `[mae]`), each of which must be registered in the metric registry. For forecasting, participants submit one list of `eval_steps` values per sensor:

```json
{
  "forecast": {
    "position": [0.12, 0.13, ...],
    "velocity": [0.01, 0.02, ...]
  }
}
```

Multi-task contests, per-task metric weighting, and the anomaly detection, fault classification, and remaining-useful-life task types are planned extensions; the task model (type, metrics, weight, configuration) already accommodates them.

### Complete Examples

A beginner contest — short observation window, clean fault-free dynamics, a single sensor pair, MAE scoring:

```yaml
name: Introductory Forecasting Challenge
twin_id: mass_spring_damper
sensor_configs:
  - sensor_id: position
    noise_std: 0.01
  - sensor_id: temperature
    noise_std: 0.3
fault_schedule: []
sampling_rate_hz: 10.0
task_type: FORECASTING
metric_ids: [mae]
score_against: ground_truth
start_date: 2027-01-10T09:00:00Z
end_of_observation: 2027-01-10T09:30:00Z   # 30-min observation window
prediction_horizon_seconds: 60.0           # predict the next 60 s (600 steps at 10 Hz)
end_date: 2027-01-10T10:00:00Z             # submission window closes 30 min later
visibility: PUBLIC
```

A graduate-level contest — noisier sensors with outliers and drift, a fault that activates mid-observation, a longer prediction horizon:

```yaml
name: Advanced Predictive Intelligence Challenge
twin_id: mass_spring_damper
sensor_configs:
  - sensor_id: position
    noise_std: 0.02
    p_outlier: 0.003
  - sensor_id: velocity
    noise_std: 0.05
  - sensor_id: temperature
    noise_std: 0.5
    drift_rate: 0.002
fault_schedule:
  - fault_id: increased_damping
    start_time: 3600.0
    end_time: null
    severity: 0.4
sampling_rate_hz: 10.0
task_type: FORECASTING
metric_ids: [mae, rmse]
score_against: ground_truth
start_date: 2027-03-01T08:00:00Z
end_of_observation: 2027-03-01T09:00:00Z   # 1-hour observation window
prediction_horizon_seconds: 300.0          # predict the next 5 min (3000 steps at 10 Hz)
end_date: 2027-03-01T12:00:00Z
visibility: PUBLIC
```

### Templates

Predefined templates exist for all five built-in twins, exposed at `GET /api/v1/templates` and loadable directly from the web UI's contest creation form. A template is a complete, validated configuration — sensor configs with realistic noise levels, a fault schedule, initial conditions, and a sampling rate — that an author can submit as-is or override parameter by parameter. User-defined reusable templates, saved and shared between organizers, are a planned extension.

### Guarantees the Author Does Not Control

Labels, fault metadata, and the twin's latent state are never exposed to participants — this is a platform-level guarantee, not a configuration option. Participants receive only sensor readings through the WebSocket stream, and the submission window only opens once the evaluation ground truth is fully recorded.

---

## Long-Term Goal

The contest framework should allow instructors and researchers to create new competitions without writing code: a contest is defined purely through configuration — twin, sensors, faults, schedule, task, metrics — while digital twins provide the underlying simulation environment. Writing code should only ever be necessary to introduce a new digital twin, sensor, fault model, metric, or task type, and each of those is a plugin.
