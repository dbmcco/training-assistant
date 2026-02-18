"""add training assistant tables

Revision ID: f59ae60687df
Revises:
Create Date: 2026-02-18 08:41:08.181427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f59ae60687df'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('athlete_profile',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('notes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('goals', sa.Text(), nullable=True),
    sa.Column('injury_history', sa.Text(), nullable=True),
    sa.Column('preferences', sa.Text(), nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('daily_briefings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('readiness_summary', sa.Text(), nullable=True),
    sa.Column('workout_recommendation', sa.Text(), nullable=True),
    sa.Column('alerts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('raw_agent_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('date')
    )
    op.create_table('gear',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('garmin_gear_uuid', sa.Text(), nullable=True),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('gear_type', sa.Text(), nullable=True),
    sa.Column('brand', sa.Text(), nullable=True),
    sa.Column('model', sa.Text(), nullable=True),
    sa.Column('date_begin', sa.Date(), nullable=True),
    sa.Column('max_distance_km', sa.Float(), nullable=True),
    sa.Column('total_distance_km', sa.Float(), nullable=True),
    sa.Column('total_activities', sa.Integer(), nullable=True),
    sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('synced_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('garmin_gear_uuid')
    )
    op.create_table('personal_records',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('record_type', sa.Text(), nullable=True),
    sa.Column('activity_type', sa.Text(), nullable=True),
    sa.Column('value', sa.Float(), nullable=True),
    sa.Column('activity_id', sa.Integer(), nullable=True),
    sa.Column('recorded_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('races',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('distance_type', sa.Text(), nullable=False),
    sa.Column('goal_time', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('activity_details',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('garmin_activity_id', sa.BigInteger(), nullable=True),
    sa.Column('splits', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('hr_zones', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('weather', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('gear_uuid', sa.Text(), nullable=True),
    sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('synced_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['garmin_activity_id'], ['garmin_activities.garmin_activity_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # Drop the legacy conversations table (from paia, different schema) and
    # recreate with the training-assistant schema.
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")
    op.create_table('conversations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('tool_calls', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('training_plan',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('race_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['race_id'], ['races.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('planned_workouts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('plan_id', sa.UUID(), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('discipline', sa.Text(), nullable=False),
    sa.Column('workout_type', sa.Text(), nullable=True),
    sa.Column('target_duration', sa.Integer(), nullable=True),
    sa.Column('target_distance', sa.Float(), nullable=True),
    sa.Column('target_hr_zone', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('completed_activity_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Text(), nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['completed_activity_id'], ['garmin_activities.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['training_plan.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('planned_workouts')
    op.drop_table('training_plan')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('activity_details')
    op.drop_table('races')
    op.drop_table('personal_records')
    op.drop_table('gear')
    op.drop_table('daily_briefings')
    op.drop_table('athlete_profile')
