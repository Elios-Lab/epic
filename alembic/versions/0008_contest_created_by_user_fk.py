"""Make contest created_by reference users."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_contest_created_by_user_fk"
down_revision = "0007_leaderboard_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("contests", "created_by")
    op.add_column(
        "contests",
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index("ix_contests_created_by", "contests", ["created_by"], unique=False)
    op.create_foreign_key(
        "fk_contests_created_by_users",
        "contests",
        "users",
        ["created_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_contests_created_by_users", "contests", type_="foreignkey")
    op.drop_index("ix_contests_created_by", table_name="contests")
    op.drop_column("contests", "created_by")
    op.add_column(
        "contests",
        sa.Column("created_by", sa.String(length=256), nullable=True),
    )
