"""Drop task_type and forecast_horizons from contests if present."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    with op.batch_alter_table("contests") as batch_op:
        if _column_exists("contests", "task_type"):
            batch_op.drop_column("task_type")
        if _column_exists("contests", "forecast_horizons"):
            batch_op.drop_column("forecast_horizons")


def downgrade() -> None:
    with op.batch_alter_table("contests") as batch_op:
        if not _column_exists("contests", "forecast_horizons"):
            batch_op.add_column(
                sa.Column("forecast_horizons", sa.JSON(), nullable=True)
            )
        if not _column_exists("contests", "task_type"):
            batch_op.add_column(
                sa.Column(
                    "task_type",
                    sa.String(length=32),
                    nullable=False,
                    server_default="FORECASTING",
                )
            )
