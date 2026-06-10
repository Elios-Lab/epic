"""User registration workflow: status field, profile fields, organizer_requests, invitations.

Replaces the boolean is_active column on users with a status string
(ACTIVE | SUSPENDED | DELETED), adds first_name / last_name /
phone_number profile fields, and introduces the organizer_requests and
invitations tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_user_registration_workflow"
down_revision = "0014_ground_truth_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users: add status + profile fields, drop is_active ────────────────
    op.add_column("users", sa.Column("status", sa.String(32), nullable=True))
    op.execute("UPDATE users SET status = CASE WHEN is_active THEN 'ACTIVE' ELSE 'SUSPENDED' END")
    op.alter_column("users", "status", nullable=False)
    op.create_index("ix_users_status", "users", ["status"])
    op.drop_column("users", "is_active")

    op.add_column("users", sa.Column("first_name", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("phone_number", sa.String(32), nullable=True))

    # ── organizer_requests ────────────────────────────────────────────────
    op.create_table(
        "organizer_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizer_requests_email", "organizer_requests", ["email"], unique=True)
    op.create_index("ix_organizer_requests_status", "organizer_requests", ["status"])

    # ── invitations ───────────────────────────────────────────────────────
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("contest_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("invited_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"]),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invitations_email", "invitations", ["email"])
    op.create_index("ix_invitations_contest_id", "invitations", ["contest_id"])
    op.create_index("ix_invitations_token", "invitations", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_invitations_token", table_name="invitations")
    op.drop_index("ix_invitations_contest_id", table_name="invitations")
    op.drop_index("ix_invitations_email", table_name="invitations")
    op.drop_table("invitations")

    op.drop_index("ix_organizer_requests_status", table_name="organizer_requests")
    op.drop_index("ix_organizer_requests_email", table_name="organizer_requests")
    op.drop_table("organizer_requests")

    op.drop_column("users", "phone_number")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")

    op.drop_index("ix_users_status", table_name="users")
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE users SET is_active = CASE WHEN status = 'ACTIVE' THEN TRUE ELSE FALSE END")
    op.alter_column("users", "is_active", nullable=False)
    op.drop_column("users", "status")
