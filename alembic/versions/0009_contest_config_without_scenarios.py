"""Move scenario configuration into contests."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_contest_config_without_scenarios"
down_revision = "0008_contest_created_by_user_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contests",
        sa.Column(
            "sensor_configs",
            sa.JSON(),
            nullable=False,
            server_default='[{"sensor_id": "position"}]',
        ),
    )
    op.add_column(
        "contests",
        sa.Column("fault_schedule", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "contests",
        sa.Column("initial_conditions", sa.JSON(), nullable=True),
    )
    op.drop_column("contests", "scenario_id")
    op.drop_column("simulation_sessions", "scenario_id")
    op.alter_column("contests", "sensor_configs", server_default=None)
    op.alter_column("contests", "fault_schedule", server_default=None)


def downgrade() -> None:
    op.add_column(
        "simulation_sessions",
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
    )
    op.add_column(
        "contests",
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
    )
    op.drop_column("contests", "initial_conditions")
    op.drop_column("contests", "fault_schedule")
    op.drop_column("contests", "sensor_configs")
