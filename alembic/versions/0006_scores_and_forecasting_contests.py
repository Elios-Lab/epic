"""Add scores and forecasting contest configuration."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_scores_and_forecasting_contests"
down_revision = "0005_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.alter_column("contests", "task_type", server_default=None)
    op.alter_column("contests", "forecast_horizons", server_default=None)

    op.create_table(
        "scores",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("submission_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("metric_id", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scores_submission_id", "scores", ["submission_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scores_submission_id", table_name="scores")
    op.drop_table("scores")
    op.drop_column("contests", "forecast_horizons")
    op.drop_column("contests", "task_type")
