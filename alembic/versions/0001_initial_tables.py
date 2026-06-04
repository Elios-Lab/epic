"""Create initial user and simulation tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("'00000000-0000-0000-0000-000000000000'"),
            nullable=False,
        ),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "simulation_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("twin_id", sa.String(length=128), nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sampling_rate_hz", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("session_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_simulation_sessions_user_id", "simulation_sessions", ["user_id"])
    op.create_index("ix_simulation_sessions_twin_id", "simulation_sessions", ["twin_id"])
    op.create_index("ix_simulation_sessions_status", "simulation_sessions", ["status"])

    op.create_table(
        "sensor_observations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sequence_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sensors", sa.JSON(), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=True),
        sa.Column("obs_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["simulation_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sensor_observations_session_id", "sensor_observations", ["session_id"])
    op.create_index("ix_sensor_observations_sequence_id", "sensor_observations", ["sequence_id"])
    op.create_index("ix_sensor_observations_timestamp", "sensor_observations", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_sensor_observations_timestamp", table_name="sensor_observations")
    op.drop_index("ix_sensor_observations_sequence_id", table_name="sensor_observations")
    op.drop_index("ix_sensor_observations_session_id", table_name="sensor_observations")
    op.drop_table("sensor_observations")
    op.drop_index("ix_simulation_sessions_status", table_name="simulation_sessions")
    op.drop_index("ix_simulation_sessions_twin_id", table_name="simulation_sessions")
    op.drop_index("ix_simulation_sessions_user_id", table_name="simulation_sessions")
    op.drop_table("simulation_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

