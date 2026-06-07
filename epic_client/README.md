# EPIC Participant SDK

`epic-elios-client` is the participant SDK for the EPIC — ELIOS Predictive Intelligence Challenge platform. It helps students and competitors authenticate, browse contests, collect live observations, submit predictions, and inspect results.

## Installation

```bash
pip install epic-elios-client
```

Install with notebook extras for the Jupyter quickstart:

```bash
pip install "epic-elios-client[notebook]"
```

## Contest format

Every EPIC contest uses a **two-phase** structure:

1. **Observation phase** (`start_date` → `end_of_observation`): the simulation runs and you receive live sensor readings via WebSocket.  Use this window to collect data and train your model.
2. **Evaluation phase** (`end_of_observation` → `end_of_observation + prediction_horizon_seconds`): the simulation continues but the stream closes.  The ground truth for this window is hidden.
3. **Submission window** (evaluation phase ends → `end_date`): submit a forecast covering every step of the evaluation window.

The number of steps to forecast is:

```
eval_steps = round(prediction_horizon_seconds × sampling_rate_hz)
```

Each sensor needs exactly `eval_steps` predicted values.

## Minimal usage

```python
import asyncio
from epic_client import EPICClient

async def main():
    client = EPICClient("https://epic.elioslab.net")
    client.login("student1", "correct-password")

    contests = client.list_contests(status="ACTIVE")
    contest_id = contests[0]["contest_id"]
    task = contests[0]["tasks"][0]           # {"eval_steps": 200, ...}
    eval_steps = task["configuration"]["eval_steps"]

    # Collect observations during the observation phase.
    observations = await client.collect(contest_id, duration_seconds=30)

    # Build a forecast once the submission window opens.
    # Predict eval_steps values for every sensor you want to score.
    sensors = list(observations[-1]["sensors"].keys())
    forecast = {sensor: [0.0] * eval_steps for sensor in sensors}

    submission = client.submit(
        contest_id=contest_id,
        task_id="forecasting",
        payload={"forecast": forecast},
    )
    print(submission)

asyncio.run(main())
```

## API reference

### `EPICClient(server_url)`

| Method | Description |
|--------|-------------|
| `login(username, password)` | Authenticate and store the bearer token. |
| `list_contests(status=None)` | Return contests, optionally filtered by status (`"ACTIVE"`, `"CLOSED"`, …). |
| `register(contest_id)` | Register for a contest (idempotent). |
| `collect(contest_id, duration_seconds, csv_path=None)` | Stream observations for up to `duration_seconds` and return them as a list. Optionally save to CSV. Stops automatically when the observation phase ends. |
| `stream(contest_id)` | Async generator that yields one observation dict per sensor tick. Stops at the end of the observation phase. |
| `submit(contest_id, task_id, payload)` | Submit a forecast. `payload` must be `{"forecast": {"sensor_id": [v1, v2, …], …}}` with exactly `eval_steps` values per sensor. |
| `get_scores(contest_id)` | Return all your submissions with their scores. |
| `get_leaderboard(contest_id)` | Return the current leaderboard. |

### Observation dict

```python
{
    "sequence_id": 42,
    "timestamp":   "2027-01-10T09:00:04.200Z",
    "sensors":     {"position": 0.134, "velocity": -0.021},
}
```

## Quickstart notebook

Download and run the
[quickstart notebook](https://github.com/Elios-Lab/epic/blob/main/notebooks/quickstart.ipynb)
for a step-by-step walkthrough.
