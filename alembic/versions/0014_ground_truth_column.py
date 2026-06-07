"""Add ground_truth column to sensor_observations.

Stores the clean latent-state values (noiseless) alongside the corrupted
sensor readings so that submissions can be evaluated against the true
physical trajectory rather than measurement noise.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sensor_observations") as batch_op:
        batch_op.add_column(sa.Column("ground_truth", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sensor_observations") as batch_op:
        batch_op.drop_column("ground_truth")
