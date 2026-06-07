"""Add end_of_observation and prediction_horizon_seconds to contests."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contests") as batch_op:
        batch_op.add_column(
            sa.Column("end_of_observation", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("prediction_horizon_seconds", sa.Float(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("contests") as batch_op:
        batch_op.drop_column("prediction_horizon_seconds")
        batch_op.drop_column("end_of_observation")
