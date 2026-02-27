"""add recommendation changes table

Revision ID: 3b2f0f4f2c71
Revises: f59ae60687df
Create Date: 2026-02-21 08:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3b2f0f4f2c71"
down_revision: Union[str, Sequence[str], None] = "f59ae60687df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "recommendation_changes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_ref_id", sa.UUID(), nullable=True),
        sa.Column("planned_workout_id", sa.UUID(), nullable=True),
        sa.Column("workout_date", sa.Date(), nullable=True),
        sa.Column("recommendation_text", sa.Text(), nullable=True),
        sa.Column("proposed_workout", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("requested_changes", sa.Text(), nullable=True),
        sa.Column("garmin_sync_status", sa.Text(), nullable=True),
        sa.Column("garmin_sync_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("garmin_sync_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("training_impact_log", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("applied_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["planned_workout_id"], ["planned_workouts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_changes_created_at",
        "recommendation_changes",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_changes_status",
        "recommendation_changes",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_recommendation_changes_source_ref_id",
        "recommendation_changes",
        ["source_ref_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_recommendation_changes_source_ref_id", table_name="recommendation_changes")
    op.drop_index("ix_recommendation_changes_status", table_name="recommendation_changes")
    op.drop_index("ix_recommendation_changes_created_at", table_name="recommendation_changes")
    op.drop_table("recommendation_changes")
