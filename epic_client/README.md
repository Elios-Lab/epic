# EPIC Participant SDK

`epic-elios-client` is the participant SDK for the EPIC — ELIOS Predictive Intelligence Challenge platform. It helps students and competitors authenticate, browse contests, collect live observations, submit predictions, and inspect results from the default EPIC server at <https://epic.elioslab.net>.

## Installation

Install the SDK:

```bash
pip install epic-elios-client
```

Install the SDK with notebook extras for the Jupyter quickstart:

```bash
pip install "epic-elios-client[notebook]"
```

## Minimal Usage

```python
import asyncio

from epic_client import EPICClient


async def main():
    client = EPICClient("https://epic.elioslab.net")
    client.login("student1", "correct-password")

    contests = client.list_contests(status="ACTIVE")
    contest_id = contests[0]["contest_id"]

    observations = await client.collect(contest_id, duration_seconds=10)
    latest = observations[-1]

    submission = client.submit(
        contest_id=contest_id,
        task_id="forecasting",
        prediction_from_sequence=latest["sequence_id"],
        payload={
            "forecast": {
                "horizon_1": latest["sensors"],
                "horizon_5": latest["sensors"],
                "horizon_10": latest["sensors"],
            }
        },
    )
    print(submission)


asyncio.run(main())
```

## Quickstart Notebook

Download and run the
[quickstart notebook](https://github.com/Elios-Lab/epic/blob/main/notebooks/quickstart.ipynb)
for a step-by-step walkthrough: connect, collect observations, plot sensor
data, and submit a prediction.
