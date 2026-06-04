# Dataset Collection

> Related: [Simulation Engine](simulation-engine.md) · [API Specification](api-specification.md) · [Contest Management](contest-management.md)

EPIC does not generate or export datasets on the server. Dataset collection is the participant's responsibility.

---

# Philosophy

A core educational principle of EPIC is that collecting data from a live system is itself a skill. Participants are expected to:

- Connect to the contest's WebSocket stream
- Decide what to record and at what granularity
- Handle connection interruptions gracefully
- Curate and engineer their own dataset for model training

This mirrors real-world industrial monitoring, where an engineer does not receive a pre-packaged dataset — they instrument the system and collect what they need.

---

# How Data Collection Works

When a contest is ACTIVE, a shared simulation runs in real wall-clock time. All participants observe the same system through the WebSocket stream (see [API Specification](api-specification.md)).

Each WebSocket message contains:

```json
{
  "timestamp": "2027-01-15T10:00:00.500Z",
  "session_id": "sess_abc",
  "sequence_id": 500,
  "sensors": {
    "position": 0.15,
    "velocity": 1.82,
    "temperature": 31.5
  }
}
```

Participants receive sensor readings only. Labels and fault information are never exposed.

---

# Client-Side Storage

Participants choose their own storage format and location. Common approaches:

- Append each message to a CSV file
- Stream into a local database (SQLite, DuckDB)
- Buffer in memory and write periodically

A minimal Python example:

```python
import asyncio
import csv
import websockets
import json

async def collect(contest_id: str, token: str, output_path: str):
    url = f"wss://epic.example.com/api/v1/ws/contests/{contest_id}?token={token}"
    with open(output_path, "w", newline="") as f:
        writer = None
        async with websockets.connect(url) as ws:
            async for message in ws:
                data = json.loads(message)
                row = {"timestamp": data["timestamp"],
                       "sequence_id": data["sequence_id"],
                       **data["sensors"]}
                if writer is None:
                    writer = csv.DictWriter(f, fieldnames=row.keys())
                    writer.writeheader()
                writer.writerow(row)
```

---

# Connection Interruptions

If a participant's connection drops, they miss the observations produced during the outage. This is intentional — it reflects real-world conditions. Participants should design their collection pipeline to reconnect automatically and handle gaps in the sequence_id.

The server does not replay missed observations.

---

# Late Joiners

A participant who connects after the contest has started will receive data from that point forward. Past observations are not accessible. This is by design: earlier participants who collected more data have a natural advantage, just as in a real monitoring scenario.

---

# Design Requirement

The EPIC platform must never be required to know how a participant stores or processes their data. The WebSocket stream is the only data delivery mechanism. All decisions about storage format, filtering, and feature engineering are client-side concerns.
