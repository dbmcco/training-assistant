"""add assistant plan entries table

Revision ID: c3f86b2dd4a1
Revises: 9d8be5d8a1c2
Create Date: 2026-03-04 11:45:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3f86b2dd4a1"
down_revision: Union[str, None] = "9d8be5d8a1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_plan_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("planned_workout_id", sa.UUID(), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("garmin_workout_id", sa.Text(), nullable=True),
        sa.Column("garmin_sync_status", sa.Text(), nullable=True),
        sa.Column("garmin_sync_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["planned_workout_id"], ["planned_workouts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("planned_workout_id"),
    )
    op.create_index(
        "ix_assistant_plan_entries_created_at",
        "assistant_plan_entries",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_assistant_plan_entries_is_locked",
        "assistant_plan_entries",
        ["is_locked"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_plan_entries_is_locked", table_name="assistant_plan_entries")
    op.drop_index("ix_assistant_plan_entries_created_at", table_name="assistant_plan_entries")
    op.drop_table("assistant_plan_entries")
