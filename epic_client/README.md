# EPIC Participant SDK

`epic-elios-client` is the official Python SDK for the **EPIC — ELIOS Predictive Intelligence Challenge** platform. EPIC is a simulation-driven machine learning competition where participants connect to live digital-twin simulations, collect sensor data in real time, build predictive models, and submit forecasts to be scored against hidden ground-truth trajectories.

This package gives you everything you need to participate: authentication, contest discovery, real-time data streaming, forecast submission, and results inspection — all from a few lines of Python, both in scripts and Jupyter notebooks.

---

## Installation

Install the SDK with pip:

```bash
pip install epic-elios-client
```

If you plan to follow the Jupyter quickstart notebook, install the optional notebook extras as well (adds `pandas` for the CSV helpers):

```bash
pip install "epic-elios-client[notebook]"
```

The SDK requires **Python 3.11 or later**.

---

## How a contest works

Every EPIC contest follows a strict **two-phase structure**. Understanding it is essential before you write any code.

### Phase 1 — Observation window

From `start_date` to `end_of_observation`, the simulation is running and broadcasting live sensor readings over a WebSocket connection. This is your data-collection window. Use `collect()` or `stream()` to receive observations and build your forecasting model.

### Phase 2 — Evaluation window

From `end_of_observation` to `end_of_observation + prediction_horizon_seconds`, the simulation keeps running but the sensor stream is closed. You can no longer receive data. The ground-truth values for this window are recorded by the platform but hidden from participants.

### Submission window

Once the evaluation window ends (and until `end_date`), you can submit your forecast. A forecast must cover **every time step** of the evaluation window for every target variable selected by the organizer.

The exact number of steps you must predict is:

```
eval_steps = round(prediction_horizon_seconds × sampling_rate_hz)
```

You can read `eval_steps` and the required `target_variables` directly from the contest's task configuration:

```python
contests = client.list_contests(status="ACTIVE")
task_spec = client.get_task_spec(contests[0]["contest_id"])
eval_steps = task_spec["eval_steps"]
target_variables = task_spec["target_variables"]
```

---

## Quickstart

The steps below walk through a complete participation cycle.

### 1. Authenticate

```python
from epic_client import EPICClient

client = EPICClient("https://epic.elioslab.net")
client.login("your-username", "your-password")
```

`login()` stores the bearer token internally. All subsequent calls are authenticated automatically.

### 2. Browse and register for a contest

```python
contests = client.list_contests(status="ACTIVE")
for c in contests:
    print(c["contest_id"], c["name"], c["sampling_rate_hz"], "Hz")

contest_id = contests[0]["contest_id"]
task_spec = client.get_task_spec(contest_id)
registration = client.register(contest_id)   # idempotent — safe to call more than once
print(registration)
```

### 3. Collect observations during the observation phase

`collect()` opens a WebSocket connection and returns a list of observation dicts when either `duration_seconds` elapses or the observation phase ends — whichever comes first.

```python
import asyncio

observations = asyncio.run(client.collect(contest_id, duration_seconds=60))
print(f"Collected {len(observations)} observations")
print(observations[-1])
# {"sequence_id": 42, "timestamp": "2027-01-10T09:01:00Z", "sensors": {"position": 0.134}}
```

You can also save to CSV for offline analysis:

```python
observations = asyncio.run(
    client.collect(contest_id, duration_seconds=60, csv_path="data.csv")
)
```

The CSV file is written with one column per sensor, for example
`sequence_id,timestamp,position,velocity`.

For finer control, use the async generator `stream()` directly:

```python
async def collect_custom():
    async for obs in client.stream(contest_id):
        print(obs["sequence_id"], obs["sensors"])
        # break early, filter, etc.

asyncio.run(collect_custom())
```

`stream()` stops automatically when the observation phase ends.
Pass `include_events=True` if you also want to receive control events such as
`evaluation_started` before the generator stops.

### 4. Build your model

Use whatever modelling approach you like. The simplest possible baseline just repeats the last observed value:

```python
last = observations[-1]["sensors"]

task_spec = client.get_task_spec(contest_id)
eval_steps = task_spec["eval_steps"]
target_variables = task_spec["target_variables"]

# Naive forecast: repeat the last observation for every step
forecast = {
    target: [last[target]] * eval_steps
    for target in target_variables
}
```

### 5. Submit your forecast

Wait until the submission window opens (evaluation phase has ended), then submit:

```python
submission = client.submit(
    contest_id=contest_id,
    task_id="forecasting",
    payload={"forecast": forecast},
)
print(submission)
```

`payload["forecast"]` must be a dict mapping each required target variable to a list of exactly `eval_steps` float values. You may submit multiple times — the platform keeps all submissions and scores each one.
If the submission window is not open yet, `submit()` returns
`{"status": "NOT_OPEN", "opens_at": "..."}` and emits a warning instead of
raising a traceback.

### 6. Check your scores and the leaderboard

```python
scores = client.get_scores(contest_id)
for sub in scores["submissions"]:
    print(sub["submission_id"], sub["scores"])

leaderboard = client.get_leaderboard(contest_id)
for entry in leaderboard["entries"]:
    print(entry["rank"], entry["username"], entry["score"])
```

---

## Complete example

```python
import asyncio
from epic_client import EPICClient

async def main():
    client = EPICClient("https://epic.elioslab.net")
    client.login("your-username", "your-password")

    # Discover the contest
    contests = client.list_contests(status="ACTIVE")
    contest = contests[0]
    contest_id = contest["contest_id"]
    task_spec = client.get_task_spec(contest_id)
    eval_steps = task_spec["eval_steps"]
    target_variables = task_spec["target_variables"]

    # Register (safe to call even if already registered)
    client.register(contest_id)

    # Collect data during the observation phase
    observations = await client.collect(contest_id, duration_seconds=120)
    print(f"Collected {len(observations)} observations")

    # Build a naive forecast (replace with your model)
    last_sensors = observations[-1]["sensors"]
    forecast = {
        sensor: [value] * eval_steps
        for sensor, value in last_sensors.items()
        if sensor in target_variables
    }

    # Submit
    submission = client.submit(
        contest_id=contest_id,
        task_id="forecasting",
        payload={"forecast": forecast},
    )
    print("Submitted:", submission["submission_id"])

    # Check scores
    scores = client.get_scores(contest_id)
    print("Scores:", scores)

asyncio.run(main())
```

---

## API reference

### `EPICClient(server_url)`

Instantiate the client by passing the server URL. Defaults to `"https://epic.elioslab.net"` if omitted.

| Method | Signature | Description |
|--------|-----------|-------------|
| `login` | `login(username, password) → dict` | Authenticate with the platform and store the bearer token for all subsequent requests. Returns the token payload. |
| `list_contests` | `list_contests(status=None, visibility=None, limit=100, offset=0) → list[dict]` | Return all contests visible to you. Pass `status="ACTIVE"` to filter to running contests only. Other values: `"DRAFT"`, `"PAUSED"`, `"CLOSED"`. |
| `get_contest` | `get_contest(contest_id) → dict` | Return the full contest object, including task configuration and sensor configuration. |
| `get_task_spec` | `get_task_spec(contest_id, task_type="FORECASTING") → dict` | Return the task plus convenience fields such as `eval_steps`, `target_variables`, `sampling_rate_hz`, and configured `sensor_ids`. |
| `register` | `register(contest_id, raise_on_not_open=False) → dict` | Register for a contest. Idempotent — calling it again on an already-registered contest is safe. If the contest is visible but not open for registration, returns `{"status": "NOT_OPEN", ...}` and emits a warning. |
| `collect` | `collect(contest_id, duration_seconds, csv_path=None) → list[dict]` | Stream observations for up to `duration_seconds` and return them as a list. Stops early if the observation phase ends. Optionally writes each observation to a CSV file as it arrives. |
| `stream` | `stream(contest_id, include_events=False) → AsyncIterator[dict]` | Async generator that yields one observation dict per sensor tick. Reconnects automatically on transient network errors. Stops when the observation phase ends. |
| `submit` | `submit(contest_id, task_id, payload, raise_on_not_open=False) → dict` | Submit a forecast. `task_id` is `"forecasting"`. `payload` must be `{"forecast": {"target_variable": [v1, v2, …], …}}` with exactly `eval_steps` values per configured target variable. |
| `get_scores` | `get_scores(contest_id) → dict` | Return all your submissions for this contest together with their computed scores. |
| `get_leaderboard` | `get_leaderboard(contest_id) → dict` | Return the current public leaderboard for this contest. |

### Observation dict

Each observation yielded by `stream()` or returned inside the list from `collect()` has this shape:

```python
{
    "sequence_id": 42,                          # monotonically increasing integer
    "committed_through": 40,                    # latest sequence durably stored by the server
    "timestamp":   "2027-01-10T09:00:04.200Z",  # UTC ISO-8601 string
    "sensors":     {                             # one key per configured sensor
        "position": 0.134,
        "velocity": -0.021,
    },
}
```

### Forecast payload

```python
{
    "forecast": {
        "position": [0.130, 0.127, 0.124, ...],  # exactly eval_steps floats
        "velocity": [-0.019, -0.018, -0.017, ...],
    }
}
```

---

## Jupyter quickstart notebook

A self-contained notebook that walks through the full participation workflow — connecting to a contest, streaming and plotting sensor data, training a simple forecasting model, and submitting predictions — is available in the repository:

[**notebooks/quickstart.ipynb**](https://github.com/Elios-Lab/epic/blob/main/notebooks/quickstart.ipynb)

To run it locally:

```bash
pip install "epic-elios-client[notebook]" jupyter
jupyter notebook notebooks/quickstart.ipynb
```
