# EPIC Participant SDK

`epic-elios-client` is the official Python SDK for the EPIC platform. It gives you everything you need to participate in a contest: authentication, contest discovery, real-time data streaming, forecast submission, and results inspection — all from a few lines of Python, in scripts and Jupyter notebooks alike.

---

## Installation

```bash
pip install epic-elios-client
```

For the Jupyter quickstart notebook, install the optional extras (adds `pandas` for the CSV helpers):

```bash
pip install "epic-elios-client[notebook]"
```

The SDK requires **Python 3.11 or later**.

---

## Quickstart

The steps below walk through a complete participation cycle. For a full narrative walkthrough with plots and model-building, see the [quickstart notebook](https://github.com/Elios-Lab/epic/blob/main/notebooks/quickstart.ipynb).

### 1. Authenticate

```python
from epic_client import EPICClient

client = EPICClient("https://epic.elioslab.net")
login = client.login("your-username", "your-password")
if login.get("status") == "ERROR":
    print("Login failed:", login["message"])
else:
    print("Logged in.")
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

The CSV file is written with one column per sensor, for example `sequence_id,timestamp,position,velocity`.

For finer control, use the async generator `stream()` directly:

```python
async def collect_custom():
    async for obs in client.stream(contest_id):
        print(obs["sequence_id"], obs["sensors"])
        # break early, filter, etc.

asyncio.run(collect_custom())
```

`stream()` stops automatically when the observation phase ends. Pass `include_events=True` to also receive control events such as `evaluation_started` before the generator stops.

### 4. Build your model

Use whatever modelling approach you like. The simplest possible baseline repeats the last observed value:

```python
last = observations[-1]["sensors"]

task_spec = client.get_task_spec(contest_id)
eval_steps = task_spec["eval_steps"]
target_variables = task_spec["target_variables"]

forecast = {
    target: [last[target]] * eval_steps
    for target in target_variables
}
```

The number of steps to predict is derived from the contest configuration:

```
eval_steps = round(prediction_horizon_seconds × sampling_rate_hz)
```

Read `eval_steps` and the required `target_variables` directly from the task spec as shown above.

### 5. Submit your forecast

Wait until the submission window opens (the evaluation phase has ended), then submit:

```python
submission = client.submit(
    contest_id=contest_id,
    task_id="forecasting",
    payload={"forecast": forecast},
)
print(submission)
```

`payload["forecast"]` must map each required target variable to a list of exactly `eval_steps` float values. You may submit multiple times — the platform scores each submission and keeps your best on the leaderboard. If the submission window is not open yet, `submit()` returns `{"status": "NOT_OPEN", "opens_at": "..."}` and emits a warning instead of raising.

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
    login = client.login("your-username", "your-password")
    if login.get("status") == "ERROR":
        print("Login failed:", login["message"])
        return

    # Discover the contest
    contests = client.list_contests(status="ACTIVE")
    contest_id = contests[0]["contest_id"]
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

## API Reference

### `EPICClient(server_url, raise_on_error=False)`

Instantiate the client by passing the server URL. Defaults to `"https://epic.elioslab.net"` if omitted. By default the SDK is notebook-friendly: expected platform states and API errors become warnings plus structured return values instead of stack traces. Pass `raise_on_error=True` when writing scripts that should fail fast.

| Method | Signature | Description |
|--------|-----------|-------------|
| `login` | `login(username, password) → dict` | Authenticate and store the bearer token for all subsequent requests. Returns the token payload, or `{"status": "ERROR", ...}` with a warning on invalid credentials. |
| `list_contests` | `list_contests(status=None, visibility=None, limit=100, offset=0) → list[dict]` | Return all contests visible to you. Pass `status="ACTIVE"` to filter to running contests. |
| `get_contest` | `get_contest(contest_id) → dict` | Return the full contest object, including task and sensor configuration. |
| `get_task_spec` | `get_task_spec(contest_id, task_type="FORECASTING") → dict` | Return the task with convenience fields: `eval_steps`, `target_variables`, `sampling_rate_hz`, and `sensor_ids`. |
| `register` | `register(contest_id, raise_on_not_open=False) → dict` | Register for a contest. Idempotent — safe to call on an already-registered contest. |
| `collect` | `collect(contest_id, duration_seconds, csv_path=None, raise_on_stream_error=False) → list[dict]` | Stream observations for up to `duration_seconds` and return them as a list. Stops early if the observation phase ends. Optionally writes to CSV as observations arrive. |
| `stream` | `stream(contest_id, include_events=False) → AsyncIterator[dict]` | Async generator yielding one observation dict per sensor tick. Reconnects on transient network errors. Stops when the observation phase ends. |
| `submit` | `submit(contest_id, task_id, payload, raise_on_not_open=False) → dict` | Submit a forecast. `task_id` is `"forecasting"`. `payload` must be `{"forecast": {"target_variable": [v1, v2, …], …}}` with exactly `eval_steps` values per target variable. |
| `get_scores` | `get_scores(contest_id) → dict` | Return all your submissions for this contest with their computed scores. |
| `get_leaderboard` | `get_leaderboard(contest_id) → dict` | Return the current public leaderboard for this contest. |

### Observation dict

Each observation yielded by `stream()` or returned in the list from `collect()`:

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
