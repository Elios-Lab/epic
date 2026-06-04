"""Add submissions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_submissions"
down_revision = "0004_contest_registrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("contest_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("prediction_from_sequence", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submission_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_submissions_contest_id", "submissions", ["contest_id"], unique=False
    )
    op.create_index("ix_submissions_user_id", "submissions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_submissions_user_id", table_name="submissions")
    op.drop_index("ix_submissions_contest_id", table_name="submissions")
    op.drop_table("submissions")
