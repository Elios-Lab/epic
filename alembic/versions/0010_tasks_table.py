"""Move contest task configuration into tasks table."""

from __future__ import annotations

import uuid
import json

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009_contest_config_without_scenarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "contest_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("contests.id"),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("metric_ids", sa.JSON(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tasks_contest_id", "tasks", ["contest_id"])

    connection = op.get_bind()
    contests = connection.execute(
        sa.text(
            "SELECT id, task_type, forecast_horizons "
            "FROM contests WHERE task_type IS NOT NULL"
        )
    )
    for contest_id, task_type, forecast_horizons in contests:
        horizons = forecast_horizons if forecast_horizons is not None else [1, 5, 10]
        if isinstance(horizons, str):
            horizons = json.loads(horizons)
        connection.execute(
            sa.text(
                "INSERT INTO tasks "
                "(id, contest_id, task_type, name, description, metric_ids, weight, configuration) "
                "VALUES (:id, :contest_id, :task_type, :name, NULL, :metric_ids, :weight, :configuration)"
            ),
            {
                "id": str(uuid.uuid4()),
                "contest_id": contest_id,
                "task_type": task_type,
                "name": task_type,
                "metric_ids": json.dumps([]),
                "weight": 1.0,
                "configuration": json.dumps({"forecast_horizons": horizons}),
            },
        )

    op.drop_column("contests", "forecast_horizons")
    op.drop_column("contests", "task_type")


def downgrade() -> None:
    op.add_column(
        "contests",
        sa.Column(
            "task_type",
            sa.String(length=32),
            nullable=False,
            server_default="FORECASTING",
        ),
    )
    op.add_column(
        "contests",
        sa.Column(
            "forecast_horizons",
            sa.JSON(),
            nullable=True,
            server_default="[1, 5, 10]",
        ),
    )

    connection = op.get_bind()
    tasks = connection.execute(
        sa.text(
            "SELECT contest_id, task_type, configuration "
            "FROM tasks ORDER BY created_at ASC"
        )
    )
    seen_contests: set[str] = set()
    for contest_id, task_type, configuration in tasks:
        if contest_id in seen_contests:
            continue
        seen_contests.add(contest_id)
        horizons = [1, 5, 10]
        if isinstance(configuration, str):
            configuration = json.loads(configuration)
        if isinstance(configuration, dict):
            horizons = configuration.get("forecast_horizons", horizons)
        connection.execute(
            sa.text(
                "UPDATE contests "
                "SET task_type = :task_type, forecast_horizons = :forecast_horizons "
                "WHERE id = :contest_id"
            ),
            {
                "task_type": task_type,
                "forecast_horizons": json.dumps(horizons),
                "contest_id": contest_id,
            },
        )

    op.alter_column("contests", "task_type", server_default=None)
    op.alter_column("contests", "forecast_horizons", server_default=None)
    op.drop_index("ix_tasks_contest_id", table_name="tasks")
    op.drop_table("tasks")
