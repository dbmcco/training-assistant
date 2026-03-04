"""add plan change events table

Revision ID: 9d8be5d8a1c2
Revises: 7a1f0c9d8b2e
Create Date: 2026-03-04 10:35:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9d8be5d8a1c2"
down_revision: Union[str, None] = "7a1f0c9d8b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plan_change_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("workout_id", sa.UUID(), nullable=True),
        sa.Column("workout_date", sa.Date(), nullable=True),
        sa.Column("previous_workout_date", sa.Date(), nullable=True),
        sa.Column("discipline", sa.Text(), nullable=True),
        sa.Column("workout_type", sa.Text(), nullable=True),
        sa.Column("changed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("previous_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("detected_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_plan_change_events_detected_at",
        "plan_change_events",
        ["detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_plan_change_events_workout_date",
        "plan_change_events",
        ["workout_date"],
        unique=False,
    )
    op.create_index(
        "ix_planned_workouts_date_status",
        "planned_workouts",
        ["date", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_planned_workouts_date_status", table_name="planned_workouts")
    op.drop_index("ix_plan_change_events_workout_date", table_name="plan_change_events")
    op.drop_index("ix_plan_change_events_detected_at", table_name="plan_change_events")
    op.drop_table("plan_change_events")
