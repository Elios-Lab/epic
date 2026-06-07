"""Drop prediction_from_sequence from submissions (two-phase only)

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-06
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("submissions") as batch_op:
        batch_op.drop_column("prediction_from_sequence")


def downgrade() -> None:
    import sqlalchemy as sa
    with op.batch_alter_table("submissions") as batch_op:
        batch_op.add_column(sa.Column("prediction_from_sequence", sa.Integer(), nullable=True))
