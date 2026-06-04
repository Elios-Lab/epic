"""Add contests and make sessions contest-owned."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_contest_owned_sessions"
down_revision = "0001_initial_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contests",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("twin_id", sa.String(length=128), nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
        sa.Column("sampling_rate_hz", sa.Float(), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contests_name", "contests", ["name"], unique=True)
    op.create_index("ix_contests_status", "contests", ["status"], unique=False)

    op.add_column(
        "simulation_sessions",
        sa.Column("contest_id", sa.Uuid(as_uuid=True), nullable=False),
    )
    op.drop_constraint(
        "simulation_sessions_user_id_fkey",
        "simulation_sessions",
        type_="foreignkey",
    )
    op.drop_index("ix_simulation_sessions_user_id", table_name="simulation_sessions")
    op.drop_column("simulation_sessions", "user_id")
    op.drop_column("simulation_sessions", "mode")
    op.drop_column("simulation_sessions", "duration_seconds")
    op.create_index(
        "ix_simulation_sessions_contest_id",
        "simulation_sessions",
        ["contest_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_simulation_sessions_contest_id_contests",
        "simulation_sessions",
        "contests",
        ["contest_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_simulation_sessions_contest_id_contests",
        "simulation_sessions",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_simulation_sessions_contest_id", table_name="simulation_sessions"
    )
    op.add_column(
        "simulation_sessions",
        sa.Column("duration_seconds", sa.Float(), nullable=False),
    )
    op.add_column(
        "simulation_sessions",
        sa.Column("mode", sa.String(length=32), nullable=False),
    )
    op.add_column(
        "simulation_sessions",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
    )
    op.create_index(
        "ix_simulation_sessions_user_id",
        "simulation_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "simulation_sessions_user_id_fkey",
        "simulation_sessions",
        "users",
        ["user_id"],
        ["id"],
    )
    op.drop_column("simulation_sessions", "contest_id")
    op.drop_index("ix_contests_status", table_name="contests")
    op.drop_index("ix_contests_name", table_name="contests")
    op.drop_table("contests")
