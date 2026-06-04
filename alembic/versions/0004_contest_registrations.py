"""Add contest registrations."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_contest_registrations"
down_revision = "0003_contest_description_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contest_registrations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("contest_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "contest_id",
            name="uq_contest_registrations_user_id_contest_id",
        ),
    )
    op.create_index(
        "ix_contest_registrations_contest_id",
        "contest_registrations",
        ["contest_id"],
        unique=False,
    )
    op.create_index(
        "ix_contest_registrations_user_id",
        "contest_registrations",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contest_registrations_user_id",
        table_name="contest_registrations",
    )
    op.drop_index(
        "ix_contest_registrations_contest_id",
        table_name="contest_registrations",
    )
    op.drop_table("contest_registrations")
