"""Add leaderboard entries."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_leaderboard_entries"
down_revision = "0006_scores_and_forecasting_contests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leaderboard_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("contest_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("submission_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contest_id",
            "user_id",
            name="uq_leaderboard_entries_contest_id_user_id",
        ),
    )
    op.create_index(
        "ix_leaderboard_entries_contest_id",
        "leaderboard_entries",
        ["contest_id"],
        unique=False,
    )
    op.create_index(
        "ix_leaderboard_entries_user_id",
        "leaderboard_entries",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_leaderboard_entries_user_id", table_name="leaderboard_entries")
    op.drop_index("ix_leaderboard_entries_contest_id", table_name="leaderboard_entries")
    op.drop_table("leaderboard_entries")
