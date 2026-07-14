"""own Garmin-backed tables in Training Assistant migrations

Revision ID: a1b2c3d4e5f6
Revises: 4e7b2a1c9d30
Create Date: 2026-07-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "4e7b2a1c9d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adopt the existing Garmin tables without dropping populated data."""
    op.execute(
        """
        ALTER TABLE garmin_daily_summary
            ADD COLUMN IF NOT EXISTS steps INTEGER,
            ADD COLUMN IF NOT EXISTS total_calories INTEGER,
            ADD COLUMN IF NOT EXISTS active_calories INTEGER,
            ADD COLUMN IF NOT EXISTS active_minutes_moderate INTEGER,
            ADD COLUMN IF NOT EXISTS active_minutes_vigorous INTEGER,
            ADD COLUMN IF NOT EXISTS respiration_avg DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS spo2_avg DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS spo2_low DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS morning_readiness_score INTEGER,
            ADD COLUMN IF NOT EXISTS daily_distance_meters DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS body_battery_events JSONB,
            ADD COLUMN IF NOT EXISTS heart_rate_zones JSONB;
        CREATE INDEX IF NOT EXISTS idx_garmin_activities_start_time
            ON garmin_activities(start_time DESC);
        CREATE INDEX IF NOT EXISTS idx_garmin_activities_activity_type
            ON garmin_activities(activity_type);
        CREATE INDEX IF NOT EXISTS idx_garmin_activities_synced_at
            ON garmin_activities(synced_at DESC);
        CREATE INDEX IF NOT EXISTS idx_garmin_daily_summary_date
            ON garmin_daily_summary(calendar_date DESC);
        CREATE INDEX IF NOT EXISTS idx_athlete_biometrics_date
            ON athlete_biometrics(date DESC);
        """
    )


def downgrade() -> None:
    """Leave populated Garmin data and shared indexes intact on downgrade."""
    pass
