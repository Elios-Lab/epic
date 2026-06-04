"""Add contest description and visibility."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_contest_description_visibility"
down_revision = "0002_contest_owned_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contests",
        sa.Column("description", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "contests",
        sa.Column(
            "visibility",
            sa.String(length=32),
            nullable=False,
            server_default="PUBLIC",
        ),
    )
    op.alter_column("contests", "visibility", server_default=None)


def downgrade() -> None:
    op.drop_column("contests", "visibility")
    op.drop_column("contests", "description")
