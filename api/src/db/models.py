from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Existing tables (read-only, must match existing schema exactly)
# ---------------------------------------------------------------------------


class GarminActivity(Base):
    __tablename__ = "garmin_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    garmin_activity_id = Column(BigInteger, unique=True)
    name = Column(Text)
    activity_type = Column(Text)
    sport_type = Column(Text)
    start_time = Column(TIMESTAMP(timezone=True))
    distance_meters = Column(Float)
    duration_seconds = Column(Float)
    elapsed_duration_seconds = Column(Float)
    elevation_gain_meters = Column(Float)
    calories = Column(Float)
    average_hr = Column(SmallInteger)
    max_hr = Column(SmallInteger)
    aerobic_training_effect = Column(Float)
    anaerobic_training_effect = Column(Float)
    avg_stroke_count = Column(Float)
    avg_swolf = Column(Float)
    pool_length_meters = Column(Float)
    average_power = Column(Float)
    normalized_power = Column(Float)
    max_power = Column(Float)
    raw_data = Column(JSONB)
    synced_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True))


class GarminDailySummary(Base):
    __tablename__ = "garmin_daily_summary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    calendar_date = Column(Date, unique=True)
    training_status = Column(Text)
    training_load_7d = Column(Float)
    training_load_28d = Column(Float)
    vo2_max_run = Column(Float)
    vo2_max_cycling = Column(Float)
    recovery_time_hours = Column(Integer)
    training_readiness_score = Column(Integer)
    body_battery_high = Column(Integer)
    body_battery_low = Column(Integer)
    body_battery_at_wake = Column(Integer)
    hrv_status = Column(Text)
    hrv_7d_avg = Column(Integer)
    hrv_last_night = Column(Integer)
    sleep_score = Column(Integer)
    sleep_duration_seconds = Column(Integer)
    sleep_quality = Column(Text)
    race_prediction_5k_seconds = Column(Integer)
    race_prediction_10k_seconds = Column(Integer)
    race_prediction_half_seconds = Column(Integer)
    race_prediction_marathon_seconds = Column(Integer)
    endurance_score = Column(Integer)
    average_stress = Column(Integer)
    resting_heart_rate = Column(Integer)
    hill_score = Column(Integer)
    raw_data = Column(JSONB)
    synced_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True))


# ---------------------------------------------------------------------------
# New tables (will be created by Alembic later)
# ---------------------------------------------------------------------------


class Race(Base):
    __tablename__ = "races"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(Text, nullable=False)
    date = Column(Date, nullable=False)
    distance_type = Column(Text, nullable=False)
    goal_time = Column(Integer)
    notes = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True))


class TrainingPlan(Base):
    __tablename__ = "training_plan"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    race_id = Column(UUID(as_uuid=True), ForeignKey("races.id"), nullable=True)
    name = Column(Text, nullable=False)
    source = Column(Text, nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    created_at = Column(TIMESTAMP(timezone=True))


class PlannedWorkout(Base):
    __tablename__ = "planned_workouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("training_plan.id"))
    date = Column(Date, nullable=False)
    discipline = Column(Text, nullable=False)
    workout_type = Column(Text)
    target_duration = Column(Integer)
    target_distance = Column(Float)
    target_hr_zone = Column(Integer)
    description = Column(Text)
    completed_activity_id = Column(
        UUID(as_uuid=True), ForeignKey("garmin_activities.id"), nullable=True
    )
    status = Column(Text, default="upcoming")
    created_at = Column(TIMESTAMP(timezone=True))


class AthleteBiometrics(Base):
    __tablename__ = "athlete_biometrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    date = Column(Date, unique=True)
    weight_kg = Column(Float)
    body_fat_pct = Column(Float)
    muscle_mass_kg = Column(Float)
    bmi = Column(Float)
    fitness_age = Column(Integer)
    actual_age = Column(Integer)
    lactate_threshold_hr = Column(Integer)
    lactate_threshold_pace = Column(Float)
    cycling_ftp = Column(Integer)
    vo2_max_detailed = Column(JSONB)
    raw_data = Column(JSONB)
    synced_at = Column(TIMESTAMP(timezone=True))


class ActivityDetail(Base):
    __tablename__ = "activity_details"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    garmin_activity_id = Column(
        BigInteger, ForeignKey("garmin_activities.garmin_activity_id")
    )
    splits = Column(JSONB)
    hr_zones = Column(JSONB)
    weather = Column(JSONB)
    gear_uuid = Column(Text)
    raw_data = Column(JSONB)
    synced_at = Column(TIMESTAMP(timezone=True))


class Gear(Base):
    __tablename__ = "gear"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    garmin_gear_uuid = Column(Text, unique=True)
    name = Column(Text)
    gear_type = Column(Text)
    brand = Column(Text)
    model = Column(Text)
    date_begin = Column(Date)
    max_distance_km = Column(Float)
    total_distance_km = Column(Float)
    total_activities = Column(Integer)
    raw_data = Column(JSONB)
    synced_at = Column(TIMESTAMP(timezone=True))


class PersonalRecord(Base):
    __tablename__ = "personal_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    record_type = Column(Text)
    activity_type = Column(Text)
    value = Column(Float)
    activity_id = Column(Integer)
    recorded_at = Column(TIMESTAMP(timezone=True))
    raw_data = Column(JSONB)


class DailyBriefing(Base):
    __tablename__ = "daily_briefings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    date = Column(Date, unique=True, nullable=False)
    content = Column(Text)
    readiness_summary = Column(Text)
    workout_recommendation = Column(Text)
    alerts = Column(JSONB)
    raw_agent_response = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True))


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True))
    updated_at = Column(TIMESTAMP(timezone=True))


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False
    )
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    tool_calls = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True))


class AthleteProfile(Base):
    __tablename__ = "athlete_profile"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    notes = Column(JSONB, default=dict)
    goals = Column(Text)
    injury_history = Column(Text)
    preferences = Column(Text)
    updated_at = Column(TIMESTAMP(timezone=True))
