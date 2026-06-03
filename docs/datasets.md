# Dataset Generation Framework

Dataset generation is one of the central educational concepts of EPIC.

Unlike traditional machine learning competitions, participants are not expected to receive a fixed dataset.

Instead, participants generate datasets by interacting with digital twins and simulation scenarios.

This approach teaches:

- Experimental design
- Data collection
- Data engineering
- Dataset curation
- Machine learning under uncertainty

The goal is to mimic real-world engineering workflows.

---

# Philosophy

Traditional workflow:

```text
Dataset
    ↓
Model
    ↓
Evaluation
```

EPIC workflow:

```text
Digital Twin
    ↓
Simulation Sessions
    ↓
Dataset Generation
    ↓
Dataset Curation
    ↓
Model Training
    ↓
Evaluation
```

Dataset generation is part of the challenge.

---

# Dataset Sources

Datasets are generated from:

- Digital Twins
- Scenarios
- Operating Profiles
- Fault Schedules
- Random Seeds

Different configurations produce different datasets.

---

# Dataset Generation Pipeline

```text
Digital Twin
      ↓
Scenario Selection
      ↓
Session Generation
      ↓
Sensor Observations
      ↓
Dataset Export
```

---

# Dataset Definition

A dataset is a collection of simulation sessions.

```python
class Dataset:

    dataset_id: str

    user_id: str

    contest_id: str | None

    twin_id: str

    scenario_ids: list[str]

    num_sessions: int

    duration_seconds: float

    sampling_rate_hz: float

    output_format: DatasetFormat

    file_path: str

    created_at: datetime

    metadata: dict
```

See [Domain Model](domain-model.md) for the full entity definition.

---

# Dataset Generation Request

Example:

```json
{
  "twin_id": "mechanical_system",
  "scenario_ids": [
    "normal_operation",
    "sensor_bias"
  ],
  "num_sessions": 100,
  "duration_seconds": 600,
  "sampling_rate_hz": 10
}
```

---

# Training Dataset Generation

Participants may create:

- Normal datasets
- Faulty datasets
- Mixed datasets

Example:

```text
80% normal
20% faulty
```

---

# Validation Dataset Generation

Participants may reserve separate scenarios or seeds.

Example:

```text
Training Seeds:
1-100

Validation Seeds:
101-120
```

This prevents data leakage.

---

# Reproducibility

Every dataset must store:

- Twin ID
- Twin Version
- Scenario IDs
- Seeds
- Sampling Rate
- Duration

This allows complete regeneration.

---

# Export Formats

Initial formats:

## CSV

Suitable for:

- Pandas
- Scikit-Learn

## JSONL

Suitable for:

- Streaming workflows
- Event-based pipelines

Future formats:

- Parquet
- Arrow
- HDF5

---

# Labels

Training datasets may contain labels.

Example:

```json
{
  "is_anomaly": true,
  "fault_type": "sensor_bias"
}
```

---

# Hidden Labels

Validation and test datasets may hide labels.

This supports contest evaluation.

---

# Dataset Metadata

Every dataset should contain:

```json
{
  "dataset_id": "...",
  "twin_id": "...",
  "num_sessions": 100,
  "sampling_rate_hz": 10
}
```

---

# Dataset Versioning

Datasets should be versioned.

Example:

```text
dataset_v1
dataset_v2
```

This supports reproducibility and benchmarking.

---

# Long-Term Goal

Dataset generation should become one of the defining features of EPIC.

Students should learn that creating high-quality datasets is often as important as building machine learning models.