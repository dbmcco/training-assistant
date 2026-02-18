# Training Assistant Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an API-first training coach with Claude Agent SDK, comprehensive Garmin sync, React dashboard, and proactive daily briefings.

**Architecture:** Python FastAPI API (all business logic, AI agent, data) + React Vite frontend (thin consumer). Shared PostgreSQL `assistant` database at `postgresql://braydon@localhost:5432/assistant`. Enhanced garmin-connect-sync for comprehensive data ingestion.

**Tech Stack:** Python 3.14 + uv, FastAPI, Claude Agent SDK, SQLAlchemy + Alembic, asyncpg. React 19 + Vite + TypeScript, Recharts, TanStack Query, Tailwind CSS.

**Design doc:** `docs/plans/2026-02-18-training-assistant-design.md`

---

## Phase 1: API Foundation

### Task 1: Scaffold API Project

**Files:**
- Create: `api/pyproject.toml`
- Create: `api/src/__init__.py`
- Create: `api/src/main.py`
- Create: `api/src/config.py`
- Create: `api/tests/__init__.py`
- Create: `api/tests/test_health.py`

**Step 1: Initialize Python project with uv**

```bash
cd /Users/braydon/projects/experiments/training-assistant
mkdir -p api/src api/tests
cd api
uv init --no-readme
```

**Step 2: Add dependencies**

```bash
cd /Users/braydon/projects/experiments/training-assistant/api
uv add fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic pydantic-settings python-dotenv sse-starlette
uv add --dev pytest pytest-asyncio httpx
```

**Step 3: Create config.py**

```python
# api/src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://braydon@localhost:5432/assistant"
    anthropic_api_key: str = ""
    coach_model: str = "claude-sonnet-4-6"
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

**Step 4: Create main.py**

```python
# api/src/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings

app = FastAPI(title="Training Assistant API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 5: Write failing test**

```python
# api/tests/test_health.py
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

**Step 6: Run test**

```bash
cd /Users/braydon/projects/experiments/training-assistant/api
uv run pytest tests/test_health.py -v
```

Expected: PASS

**Step 7: Create .env**

```bash
# api/.env
DATABASE_URL=postgresql+asyncpg://braydon@localhost:5432/assistant
ANTHROPIC_API_KEY=<from existing config>
```

**Step 8: Verify server starts**

```bash
cd /Users/braydon/projects/experiments/training-assistant/api
uv run uvicorn src.main:app --port 8000
# Visit http://localhost:8000/health -> {"status": "ok"}
# Visit http://localhost:8000/docs -> Swagger UI
```

**Step 9: Commit**

```bash
git add api/
git commit -m "feat: scaffold FastAPI project with health endpoint"
```

---

### Task 2: Database Connection + Base Models

**Files:**
- Create: `api/src/db/__init__.py`
- Create: `api/src/db/connection.py`
- Create: `api/src/db/models.py`
- Create: `api/tests/test_db.py`

**Step 1: Create async database connection**

```python
# api/src/db/connection.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session
```

**Step 2: Create SQLAlchemy models for existing Garmin tables + new tables**

```python
# api/src/db/models.py
from datetime import date, datetime
from uuid import uuid4
from sqlalchemy import Column, String, Integer, Float, DateTime, Date, Text, ForeignKey, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

# --- Existing Garmin tables (read-only, reflect existing schema) ---

class GarminActivity(Base):
    __tablename__ = "garmin_activities"
    id = Column(UUID, primary_key=True, default=uuid4)
    garmin_activity_id = Column(Integer, unique=True, nullable=False)
    name = Column(Text)
    activity_type = Column(Text)
    sport_type = Column(Text)
    start_time = Column(DateTime(timezone=True))
    distance_meters = Column(Float)
    duration_seconds = Column(Float)
    elapsed_duration_seconds = Column(Float)
    elevation_gain_meters = Column(Float)
    calories = Column(Float)
    average_hr = Column(Integer)
    max_hr = Column(Integer)
    aerobic_training_effect = Column(Float)
    anaerobic_training_effect = Column(Float)
    avg_stroke_count = Column(Float)
    avg_swolf = Column(Float)
    pool_length_meters = Column(Float)
    average_power = Column(Float)
    normalized_power = Column(Float)
    max_power = Column(Float)
    raw_data = Column(JSONB, default={})
    synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True))

class GarminDailySummary(Base):
    __tablename__ = "garmin_daily_summary"
    id = Column(UUID, primary_key=True, default=uuid4)
    calendar_date = Column(Date, unique=True, nullable=False)
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
    raw_data = Column(JSONB, default={})
    synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True))

# --- New tables (managed by Alembic) ---

class Race(Base):
    __tablename__ = "races"
    id = Column(UUID, primary_key=True, default=uuid4)
    name = Column(Text, nullable=False)
    date = Column(Date, nullable=False)
    distance_type = Column(Text, nullable=False)  # half_iron, marathon, sprint_tri, etc.
    goal_time = Column(Integer)  # seconds
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class TrainingPlan(Base):
    __tablename__ = "training_plan"
    id = Column(UUID, primary_key=True, default=uuid4)
    race_id = Column(UUID, ForeignKey("races.id"), nullable=True)
    name = Column(Text, nullable=False)
    source = Column(Text, nullable=False)  # garmin, custom, ai
    start_date = Column(Date)
    end_date = Column(Date)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class PlannedWorkout(Base):
    __tablename__ = "planned_workouts"
    id = Column(UUID, primary_key=True, default=uuid4)
    plan_id = Column(UUID, ForeignKey("training_plan.id"))
    date = Column(Date, nullable=False)
    discipline = Column(Text, nullable=False)  # swim, bike, run, strength, rest
    workout_type = Column(Text)  # easy, tempo, intervals, long, brick
    target_duration = Column(Integer)  # seconds
    target_distance = Column(Float)  # meters
    target_hr_zone = Column(Integer)
    description = Column(Text)
    completed_activity_id = Column(UUID, ForeignKey("garmin_activities.id"), nullable=True)
    status = Column(Text, default="upcoming")  # upcoming, completed, missed, skipped, modified
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class AthleteBiometrics(Base):
    __tablename__ = "athlete_biometrics"
    id = Column(UUID, primary_key=True, default=uuid4)
    date = Column(Date, nullable=False, unique=True)
    weight_kg = Column(Float)
    body_fat_pct = Column(Float)
    muscle_mass_kg = Column(Float)
    bmi = Column(Float)
    fitness_age = Column(Integer)
    actual_age = Column(Integer)
    lactate_threshold_hr = Column(Integer)
    lactate_threshold_pace = Column(Float)  # min/km
    cycling_ftp = Column(Integer)
    vo2_max_detailed = Column(JSONB)
    raw_data = Column(JSONB, default={})
    synced_at = Column(DateTime(timezone=True))

class ActivityDetail(Base):
    __tablename__ = "activity_details"
    id = Column(UUID, primary_key=True, default=uuid4)
    garmin_activity_id = Column(Integer, ForeignKey("garmin_activities.garmin_activity_id"))
    splits = Column(JSONB)
    hr_zones = Column(JSONB)
    weather = Column(JSONB)
    gear_uuid = Column(Text)
    raw_data = Column(JSONB, default={})
    synced_at = Column(DateTime(timezone=True))

class Gear(Base):
    __tablename__ = "gear"
    id = Column(UUID, primary_key=True, default=uuid4)
    garmin_gear_uuid = Column(Text, unique=True)
    name = Column(Text)
    gear_type = Column(Text)
    brand = Column(Text)
    model = Column(Text)
    date_begin = Column(Date)
    max_distance_km = Column(Float)
    total_distance_km = Column(Float)
    total_activities = Column(Integer)
    raw_data = Column(JSONB, default={})
    synced_at = Column(DateTime(timezone=True))

class PersonalRecord(Base):
    __tablename__ = "personal_records"
    id = Column(UUID, primary_key=True, default=uuid4)
    record_type = Column(Text)
    activity_type = Column(Text)
    value = Column(Float)
    activity_id = Column(Integer)
    recorded_at = Column(DateTime(timezone=True))
    raw_data = Column(JSONB, default={})

class DailyBriefing(Base):
    __tablename__ = "daily_briefings"
    id = Column(UUID, primary_key=True, default=uuid4)
    date = Column(Date, unique=True, nullable=False)
    content = Column(Text)
    readiness_summary = Column(Text)
    workout_recommendation = Column(Text)
    alerts = Column(JSONB)
    raw_agent_response = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(UUID, primary_key=True, default=uuid4)
    title = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID, primary_key=True, default=uuid4)
    conversation_id = Column(UUID, ForeignKey("conversations.id"), nullable=False)
    role = Column(Text, nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    tool_calls = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class AthleteProfile(Base):
    __tablename__ = "athlete_profile"
    id = Column(UUID, primary_key=True, default=uuid4)
    notes = Column(JSONB, default={})
    goals = Column(Text)
    injury_history = Column(Text)
    preferences = Column(Text)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
```

**Step 3: Write test that verifies DB connection and existing Garmin data**

```python
# api/tests/test_db.py
import pytest
from sqlalchemy import select, func
from src.db.connection import async_session
from src.db.models import GarminActivity, GarminDailySummary

@pytest.mark.asyncio
async def test_can_read_garmin_activities():
    async with async_session() as session:
        result = await session.execute(select(func.count()).select_from(GarminActivity))
        count = result.scalar()
    assert count > 0, "Expected existing garmin_activities rows"

@pytest.mark.asyncio
async def test_can_read_garmin_daily_summary():
    async with async_session() as session:
        result = await session.execute(select(func.count()).select_from(GarminDailySummary))
        count = result.scalar()
    assert count > 0, "Expected existing garmin_daily_summary rows"
```

**Step 4: Run tests**

```bash
cd /Users/braydon/projects/experiments/training-assistant/api
uv run pytest tests/test_db.py -v
```

Expected: PASS (verifies connection to existing `assistant` DB)

**Step 5: Commit**

```bash
git add api/src/db/ api/tests/test_db.py
git commit -m "feat: database connection and SQLAlchemy models"
```

---

### Task 3: Alembic Migrations for New Tables

**Files:**
- Create: `api/alembic.ini`
- Create: `api/src/db/migrations/env.py`
- Create: `api/src/db/migrations/versions/001_initial.py`

**Step 1: Initialize Alembic**

```bash
cd /Users/braydon/projects/experiments/training-assistant/api
uv run alembic init src/db/migrations
```

**Step 2: Configure alembic.ini**

Edit `alembic.ini`: set `sqlalchemy.url = postgresql://braydon@localhost:5432/assistant`

**Step 3: Edit migrations/env.py**

Add `target_metadata = Base.metadata` and import models. Configure to skip existing Garmin tables (they're managed by sync.py, not Alembic).

**Step 4: Generate migration**

```bash
uv run alembic revision --autogenerate -m "add training assistant tables"
```

Review the generated migration — it should create: `races`, `training_plan`, `planned_workouts`, `athlete_biometrics`, `activity_details`, `gear`, `personal_records`, `daily_briefings`, `conversations`, `messages`, `athlete_profile`. It should NOT touch `garmin_activities` or `garmin_daily_summary`.

**Step 5: Run migration**

```bash
uv run alembic upgrade head
```

**Step 6: Verify tables exist**

```bash
/opt/homebrew/Cellar/postgresql@17/17.7_1/bin/psql -U braydon -d assistant -c '\dt races'
```

Expected: table listed

**Step 7: Commit**

```bash
git add api/alembic.ini api/src/db/migrations/
git commit -m "feat: Alembic migrations for training assistant tables"
```

---

## Phase 2: Enhanced Garmin Sync

### Task 4: Comprehensive Sync — Athlete Biometrics (Tier 1)

**Files:**
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/sync.py`
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/schema.sql`

**Step 1: Add `athlete_biometrics` table to schema.sql**

Append to schema.sql:

```sql
CREATE TABLE IF NOT EXISTS athlete_biometrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date DATE NOT NULL UNIQUE,
  weight_kg DOUBLE PRECISION,
  body_fat_pct DOUBLE PRECISION,
  muscle_mass_kg DOUBLE PRECISION,
  bmi DOUBLE PRECISION,
  fitness_age INTEGER,
  actual_age INTEGER,
  lactate_threshold_hr INTEGER,
  lactate_threshold_pace DOUBLE PRECISION,
  cycling_ftp INTEGER,
  vo2_max_detailed JSONB,
  raw_data JSONB DEFAULT '{}'::jsonb,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_athlete_biometrics_date
  ON athlete_biometrics(date DESC);
```

**Step 2: Add `sync_biometrics` method to GarminSyncClient in sync.py**

```python
def sync_biometrics(self, target_date: date) -> bool:
    """Fetch athlete profile, body comp, fitness age, thresholds."""
    date_str = target_date.isoformat()
    print(f"  Fetching biometrics for {date_str}...")

    user_profile = self._safe_get("get_user_profile")
    body_comp = self._safe_get("get_body_composition", date_str)
    fitness_age = self._safe_get("get_fitnessage_data", date_str)
    max_metrics = self._safe_get("get_max_metrics", date_str)
    lactate = self._safe_get("get_lactate_threshold", latest=True)
    ftp = self._safe_get("get_cycling_ftp")
    personal_records = self._safe_get("get_personal_record")
    goals = self._safe_get("get_goals", status="active")

    # Extract weight/body comp
    weight_kg = None
    body_fat_pct = None
    muscle_mass_kg = None
    bmi_val = None
    if isinstance(body_comp, dict):
        weight_list = body_comp.get("dateWeightList") or []
        if weight_list:
            latest = weight_list[-1]
            weight_kg = latest.get("weight") / 1000.0 if latest.get("weight") else None
            bmi_val = latest.get("bmi")
        body_fat_pct = body_comp.get("totalAverage", {}).get("fatPercentage")
        muscle_mass_kg = body_comp.get("totalAverage", {}).get("muscleMass")

    # Extract fitness age
    fitness_age_val = None
    actual_age_val = None
    if isinstance(fitness_age, dict):
        fitness_age_val = fitness_age.get("fitnessAge")
        actual_age_val = fitness_age.get("chronologicalAge")

    # Extract lactate threshold
    lt_hr = None
    lt_pace = None
    if isinstance(lactate, dict):
        lt_hr = lactate.get("lactateThresholdHeartRate")
        lt_pace = lactate.get("runningLactateThresholdPace")

    # Extract FTP
    ftp_val = None
    if isinstance(ftp, dict):
        ftp_val = ftp.get("ftpValue")

    raw = {}
    for key, val in [("user_profile", user_profile), ("body_comp", body_comp),
                      ("fitness_age", fitness_age), ("max_metrics", max_metrics),
                      ("lactate", lactate), ("ftp", ftp),
                      ("personal_records", personal_records), ("goals", goals)]:
        if val:
            raw[key] = val

    try:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO athlete_biometrics (
                date, weight_kg, body_fat_pct, muscle_mass_kg, bmi,
                fitness_age, actual_age, lactate_threshold_hr,
                lactate_threshold_pace, cycling_ftp, vo2_max_detailed,
                raw_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (date) DO UPDATE SET
                weight_kg = EXCLUDED.weight_kg,
                body_fat_pct = EXCLUDED.body_fat_pct,
                muscle_mass_kg = EXCLUDED.muscle_mass_kg,
                bmi = EXCLUDED.bmi,
                fitness_age = EXCLUDED.fitness_age,
                actual_age = EXCLUDED.actual_age,
                lactate_threshold_hr = EXCLUDED.lactate_threshold_hr,
                lactate_threshold_pace = EXCLUDED.lactate_threshold_pace,
                cycling_ftp = EXCLUDED.cycling_ftp,
                vo2_max_detailed = EXCLUDED.vo2_max_detailed,
                raw_data = EXCLUDED.raw_data,
                synced_at = NOW()
        """, (
            target_date, weight_kg, body_fat_pct, muscle_mass_kg, bmi_val,
            fitness_age_val, actual_age_val, lt_hr, lt_pace, ftp_val,
            json.dumps(max_metrics) if max_metrics else "{}",
            json.dumps(raw),
        ))
        self.conn.commit()
        print(f"    Saved biometrics for {date_str}.")
        return True
    except Exception as e:
        print(f"    [error] Failed to save biometrics for {date_str}: {e}")
        self.conn.rollback()
        return False
```

**Step 3: Add `--comprehensive` flag to CLI and call sync_biometrics from full_sync**

Add to `full_sync()`:

```python
if comprehensive:
    print(f"\nSyncing biometrics...")
    self.sync_biometrics(date.today())
```

**Step 4: Test manually**

```bash
cd /Users/braydon/projects/experiments/garmin-connect-sync
source .venv/bin/activate
python sync.py --comprehensive --days-back 1
```

Verify biometrics row created:
```bash
/opt/homebrew/Cellar/postgresql@17/17.7_1/bin/psql -U braydon -d assistant -c "SELECT date, weight_kg, fitness_age, cycling_ftp FROM athlete_biometrics ORDER BY date DESC LIMIT 1"
```

**Step 5: Commit**

```bash
cd /Users/braydon/projects/experiments/garmin-connect-sync
git add sync.py schema.sql
git commit -m "feat: add comprehensive biometrics sync (Tier 1)"
```

---

### Task 5: Comprehensive Sync — Expanded Daily Wellness (Tier 2)

**Files:**
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/sync.py`
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/schema.sql`

**Step 1: Add new columns to garmin_daily_summary**

Create migration SQL (run manually or add to schema.sql):

```sql
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
```

**Step 2: Expand `sync_daily_summary` to fetch additional endpoints**

Add these calls inside `sync_daily_summary`:

```python
user_summary = self._safe_get("get_user_summary", date_str)
respiration = self._safe_get("get_respiration_data", date_str)
spo2 = self._safe_get("get_spo2_data", date_str)
intensity = self._safe_get("get_intensity_minutes_data", date_str)
heart_rates = self._safe_get("get_heart_rates", date_str)
bb_events = self._safe_get("get_body_battery_events", date_str)
morning_readiness = self._safe_get("get_morning_training_readiness", date_str)
```

Extract values and add to the INSERT/UPSERT statement.

**Step 3: Test**

```bash
python sync.py --daily-only --days-back 1
```

Verify new columns populated:
```bash
/opt/homebrew/Cellar/postgresql@17/17.7_1/bin/psql -U braydon -d assistant -c "SELECT calendar_date, steps, respiration_avg, spo2_avg, morning_readiness_score FROM garmin_daily_summary ORDER BY calendar_date DESC LIMIT 3"
```

**Step 4: Commit**

```bash
git commit -am "feat: expand daily wellness sync with Tier 2 data"
```

---

### Task 6: Comprehensive Sync — Training Plans from Garmin (Tier 3)

**Files:**
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/sync.py`
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/schema.sql`

**Step 1: Add tables to schema.sql**

```sql
CREATE TABLE IF NOT EXISTS garmin_training_plans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  garmin_plan_id TEXT NOT NULL UNIQUE,
  name TEXT,
  plan_type TEXT,
  start_date DATE,
  end_date DATE,
  raw_data JSONB DEFAULT '{}'::jsonb,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS garmin_planned_workouts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  garmin_workout_id TEXT NOT NULL UNIQUE,
  plan_id TEXT,
  date DATE,
  discipline TEXT,
  workout_type TEXT,
  description TEXT,
  target_data JSONB,
  raw_data JSONB DEFAULT '{}'::jsonb,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Step 2: Add `sync_training_plans` method**

```python
def sync_training_plans(self) -> int:
    """Fetch training plans and saved workouts from Garmin."""
    print("Fetching training plans...")
    plans = self._safe_get("get_training_plans")
    if not plans:
        print("  No training plans found.")
        return 0

    synced = 0
    cur = self.conn.cursor()

    plan_list = plans if isinstance(plans, list) else [plans]
    for plan in plan_list:
        plan_id = str(plan.get("trainingPlanId") or plan.get("id", ""))
        if not plan_id:
            continue
        try:
            cur.execute("""
                INSERT INTO garmin_training_plans (garmin_plan_id, name, plan_type, raw_data)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (garmin_plan_id) DO UPDATE SET
                    name = EXCLUDED.name, raw_data = EXCLUDED.raw_data, synced_at = NOW()
            """, (plan_id, plan.get("name"), plan.get("type"), json.dumps(plan)))
            synced += 1
        except Exception as e:
            print(f"  [warn] Plan {plan_id} failed: {e}")
            self.conn.rollback()

    # Also fetch saved workouts
    workouts = self._safe_get("get_workouts", 0, 200)
    if workouts:
        workout_list = workouts if isinstance(workouts, list) else []
        for w in workout_list:
            wid = str(w.get("workoutId", ""))
            if not wid:
                continue
            try:
                cur.execute("""
                    INSERT INTO garmin_planned_workouts (garmin_workout_id, workout_type, description, raw_data)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (garmin_workout_id) DO UPDATE SET
                        workout_type = EXCLUDED.workout_type, raw_data = EXCLUDED.raw_data, synced_at = NOW()
                """, (wid, w.get("sportType", {}).get("sportTypeKey"), w.get("workoutName"), json.dumps(w)))
            except Exception as e:
                print(f"  [warn] Workout {wid} failed: {e}")
                self.conn.rollback()

    self.conn.commit()
    print(f"  Synced {synced} training plans.")
    return synced
```

**Step 3: Add to full_sync comprehensive path, test, commit**

```bash
python sync.py --comprehensive --days-back 1
git commit -am "feat: sync Garmin training plans and workouts (Tier 3)"
```

---

### Task 7: Comprehensive Sync — Activity Details (Tier 4)

**Files:**
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/sync.py`
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/schema.sql`

**Step 1: Add `activity_details` table to schema.sql**

```sql
CREATE TABLE IF NOT EXISTS activity_details (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  garmin_activity_id BIGINT NOT NULL UNIQUE REFERENCES garmin_activities(garmin_activity_id),
  splits JSONB,
  hr_zones JSONB,
  weather JSONB,
  gear_uuid TEXT,
  raw_data JSONB DEFAULT '{}'::jsonb,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Step 2: Add `sync_activity_details` method**

For each recently synced activity that doesn't have a detail row yet, fetch splits, HR zones, weather, and gear. Rate limit with `_delay()` between calls.

```python
def sync_activity_details(self, days_back: int = 3) -> int:
    """Enrich recent activities with splits, HR zones, weather, gear."""
    print("Enriching activity details...")
    cur = self.conn.cursor()
    cur.execute("""
        SELECT ga.garmin_activity_id FROM garmin_activities ga
        LEFT JOIN activity_details ad ON ga.garmin_activity_id = ad.garmin_activity_id
        WHERE ad.id IS NULL AND ga.start_time > NOW() - INTERVAL '%s days'
        ORDER BY ga.start_time DESC
    """, (days_back,))
    activity_ids = [row[0] for row in cur.fetchall()]

    if not activity_ids:
        print("  No new activities to enrich.")
        return 0

    synced = 0
    for aid in activity_ids:
        aid_str = str(aid)
        splits = self._safe_get("get_activity_splits", aid_str)
        hr_zones = self._safe_get("get_activity_hr_in_timezones", aid_str)
        weather = self._safe_get("get_activity_weather", aid_str)
        gear = self._safe_get("get_activity_gear", aid_str)

        gear_uuid = None
        if isinstance(gear, list) and gear:
            gear_uuid = gear[0].get("uuid")

        raw = {"splits": splits, "hr_zones": hr_zones, "weather": weather, "gear": gear}

        try:
            cur.execute("""
                INSERT INTO activity_details (garmin_activity_id, splits, hr_zones, weather, gear_uuid, raw_data)
                VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb)
                ON CONFLICT (garmin_activity_id) DO UPDATE SET
                    splits = EXCLUDED.splits, hr_zones = EXCLUDED.hr_zones,
                    weather = EXCLUDED.weather, gear_uuid = EXCLUDED.gear_uuid,
                    raw_data = EXCLUDED.raw_data, synced_at = NOW()
            """, (aid, json.dumps(splits), json.dumps(hr_zones),
                  json.dumps(weather), gear_uuid, json.dumps(raw)))
            synced += 1
        except Exception as e:
            print(f"  [warn] Activity detail {aid} failed: {e}")
            self.conn.rollback()

    self.conn.commit()
    print(f"  Enriched {synced}/{len(activity_ids)} activities.")
    return synced
```

**Step 3: Test, commit**

```bash
python sync.py --comprehensive --days-back 7
git commit -am "feat: activity detail enrichment with splits, HR zones, weather (Tier 4)"
```

---

### Task 8: Comprehensive Sync — Gear Tracking (Tier 5)

**Files:**
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/sync.py`
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/schema.sql`

**Step 1: Add `gear` table to schema.sql** (see design doc for schema)

**Step 2: Add `sync_gear` method**

Fetch user profile number from `get_user_profile()`, then `get_gear(profile_number)`, then `get_gear_stats(uuid)` for each item. Upsert to `gear` table.

**Step 3: Test, commit**

```bash
python sync.py --comprehensive --days-back 1
git commit -am "feat: gear tracking sync (Tier 5)"
```

---

## Phase 3: Core API Services

### Task 9: Readiness Scoring Service

**Files:**
- Create: `api/src/services/__init__.py`
- Create: `api/src/services/readiness.py`
- Create: `api/tests/test_readiness.py`

**Step 1: Write failing test**

```python
# api/tests/test_readiness.py
import pytest
from src.services.readiness import compute_readiness, ReadinessScore

def test_readiness_all_good():
    score = compute_readiness(
        hrv_last_night=50, hrv_7d_avg=48,
        sleep_score=85, body_battery_wake=75,
        recovery_time_hours=0,
        training_load_7d=500, training_load_28d=450,
    )
    assert isinstance(score, ReadinessScore)
    assert 70 <= score.score <= 100
    assert score.label in ("High", "Moderate", "Low")

def test_readiness_overtrained():
    score = compute_readiness(
        hrv_last_night=30, hrv_7d_avg=48,
        sleep_score=45, body_battery_wake=25,
        recovery_time_hours=48,
        training_load_7d=800, training_load_28d=400,
    )
    assert score.score < 50
    assert score.label == "Low"

def test_readiness_missing_data_graceful():
    score = compute_readiness(
        hrv_last_night=None, hrv_7d_avg=None,
        sleep_score=70, body_battery_wake=60,
        recovery_time_hours=None,
        training_load_7d=None, training_load_28d=None,
    )
    assert score.score > 0  # Still produces a score from available data
```

**Step 2: Run tests, verify fail**

```bash
uv run pytest tests/test_readiness.py -v
```

**Step 3: Implement**

```python
# api/src/services/readiness.py
from dataclasses import dataclass

@dataclass
class ReadinessComponent:
    name: str
    value: float | None
    normalized: float  # 0-100
    weight: float
    detail: str

@dataclass
class ReadinessScore:
    score: int  # 0-100
    label: str  # High, Moderate, Low
    components: list[ReadinessComponent]

def compute_readiness(
    hrv_last_night: int | None,
    hrv_7d_avg: int | None,
    sleep_score: int | None,
    body_battery_wake: int | None,
    recovery_time_hours: int | None,
    training_load_7d: float | None,
    training_load_28d: float | None,
) -> ReadinessScore:
    components = []
    total_weight = 0.0

    # HRV component (25%) — compare last night to 7-day average
    if hrv_last_night is not None and hrv_7d_avg is not None and hrv_7d_avg > 0:
        ratio = hrv_last_night / hrv_7d_avg
        hrv_norm = min(100, max(0, ratio * 100))
        components.append(ReadinessComponent(
            "hrv", hrv_last_night, hrv_norm, 0.25,
            f"{hrv_last_night}ms vs {hrv_7d_avg}ms avg"
        ))
        total_weight += 0.25

    # Sleep component (20%)
    if sleep_score is not None:
        components.append(ReadinessComponent(
            "sleep", sleep_score, min(100, float(sleep_score)), 0.20,
            f"Sleep score: {sleep_score}"
        ))
        total_weight += 0.20

    # Body battery component (20%)
    if body_battery_wake is not None:
        components.append(ReadinessComponent(
            "body_battery", body_battery_wake, float(body_battery_wake), 0.20,
            f"Woke at {body_battery_wake}"
        ))
        total_weight += 0.20

    # Recovery time component (15%) — 0 hours = 100, 48+ = 0
    if recovery_time_hours is not None:
        rec_norm = max(0, 100 - (recovery_time_hours / 48 * 100))
        components.append(ReadinessComponent(
            "recovery", recovery_time_hours, rec_norm, 0.15,
            f"{recovery_time_hours}h recovery needed"
        ))
        total_weight += 0.15

    # Load balance component (20%) — acute:chronic ratio, ideal ~1.0-1.2
    if training_load_7d is not None and training_load_28d is not None and training_load_28d > 0:
        acr = training_load_7d / training_load_28d
        # 0.8-1.2 = good (100), >1.5 = bad (0), <0.5 = detraining (50)
        if 0.8 <= acr <= 1.2:
            load_norm = 100.0
        elif acr > 1.2:
            load_norm = max(0, 100 - ((acr - 1.2) / 0.3 * 100))
        else:
            load_norm = max(0, 50 + (acr / 0.8 * 50))
        components.append(ReadinessComponent(
            "load_balance", acr, load_norm, 0.20,
            f"Acute/chronic ratio: {acr:.2f}"
        ))
        total_weight += 0.20

    # Compute weighted score, redistributing weight if some components missing
    if total_weight == 0:
        return ReadinessScore(50, "Moderate", [])

    weighted_sum = sum(c.normalized * (c.weight / total_weight) for c in components)
    score = int(round(weighted_sum))

    if score >= 70:
        label = "High"
    elif score >= 45:
        label = "Moderate"
    else:
        label = "Low"

    return ReadinessScore(score=score, label=label, components=components)
```

**Step 4: Run tests, verify pass**

```bash
uv run pytest tests/test_readiness.py -v
```

**Step 5: Commit**

```bash
git add api/src/services/ api/tests/test_readiness.py
git commit -m "feat: readiness scoring service with weighted components"
```

---

### Task 10: Analytics Service (Load, Volume, Trends)

**Files:**
- Create: `api/src/services/analytics.py`
- Create: `api/tests/test_analytics.py`

**Step 1: Write failing tests for key calculations**

Test `weekly_volume_by_discipline()`, `training_load_trend()`, and `race_projection()`.

**Step 2: Implement analytics service**

Key functions:
- `weekly_volume_by_discipline(session, start, end)` — aggregates hours + distance by swim/bike/run/other from `garmin_activities`
- `training_load_trend(session, weeks)` — returns weekly acute/chronic load from `garmin_daily_summary`
- `plan_adherence(session, plan_id, start, end)` — compares `planned_workouts` to `garmin_activities`, returns completion %
- `race_projection(session, race_id)` — weeks out, current fitness trajectory, predicted finish based on Garmin race predictions

**Step 3: Run tests, commit**

```bash
uv run pytest tests/test_analytics.py -v
git commit -am "feat: analytics service for volume, load, adherence, projections"
```

---

### Task 11: Plan Engine Service

**Files:**
- Create: `api/src/services/plan_engine.py`
- Create: `api/tests/test_plan_engine.py`

**Step 1: Tests for plan import and workout matching**

**Step 2: Implement**

Key functions:
- `import_garmin_plan(session)` — reads `garmin_training_plans` and `garmin_planned_workouts`, creates corresponding `training_plan` + `planned_workouts` rows
- `match_workouts_to_activities(session, plan_id, date_range)` — for each `planned_workout`, find the best matching `garmin_activity` by date + discipline + duration. Set `completed_activity_id` and `status`
- `get_today_workout(session, plan_id)` — return today's planned workout with completion status

**Step 3: Tests pass, commit**

```bash
git commit -am "feat: plan engine with Garmin import and workout matching"
```

---

## Phase 4: API Routes

### Task 12: Dashboard Routes

**Files:**
- Create: `api/src/routers/__init__.py`
- Create: `api/src/routers/dashboard.py`
- Create: `api/tests/test_dashboard_routes.py`
- Modify: `api/src/main.py` (register router)

**Step 1: Write failing test for `/api/v1/dashboard/today`**

```python
# api/tests/test_dashboard_routes.py
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app

@pytest.mark.asyncio
async def test_dashboard_today():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/dashboard/today")
    assert resp.status_code == 200
    data = resp.json()
    assert "readiness" in data
    assert "date" in data
```

**Step 2: Implement dashboard router**

```python
# api/src/routers/dashboard.py
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.db.connection import get_db
from src.db.models import GarminDailySummary, PlannedWorkout, Race, DailyBriefing
from src.services.readiness import compute_readiness
from src.services.analytics import weekly_volume_by_discipline

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

@router.get("/today")
async def dashboard_today(db: AsyncSession = Depends(get_db)):
    today = date.today()

    # Get latest daily summary
    result = await db.execute(
        select(GarminDailySummary)
        .where(GarminDailySummary.calendar_date <= today)
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    summary = result.scalar_one_or_none()

    readiness = compute_readiness(
        hrv_last_night=summary.hrv_last_night if summary else None,
        hrv_7d_avg=summary.hrv_7d_avg if summary else None,
        sleep_score=summary.sleep_score if summary else None,
        body_battery_wake=summary.body_battery_at_wake if summary else None,
        recovery_time_hours=summary.recovery_time_hours if summary else None,
        training_load_7d=summary.training_load_7d if summary else None,
        training_load_28d=summary.training_load_28d if summary else None,
    )

    # Today's workout
    workout_result = await db.execute(
        select(PlannedWorkout)
        .where(PlannedWorkout.date == today)
        .limit(1)
    )
    today_workout = workout_result.scalar_one_or_none()

    # Upcoming races
    race_result = await db.execute(
        select(Race).where(Race.date >= today).order_by(Race.date)
    )
    races = race_result.scalars().all()

    # Latest briefing
    briefing_result = await db.execute(
        select(DailyBriefing).where(DailyBriefing.date == today)
    )
    briefing = briefing_result.scalar_one_or_none()

    return {
        "date": today.isoformat(),
        "readiness": {
            "score": readiness.score,
            "label": readiness.label,
            "components": [
                {"name": c.name, "value": c.value, "normalized": c.normalized,
                 "weight": c.weight, "detail": c.detail}
                for c in readiness.components
            ],
        },
        "today_workout": {
            "discipline": today_workout.discipline,
            "type": today_workout.workout_type,
            "target_duration": today_workout.target_duration,
            "description": today_workout.description,
            "status": today_workout.status,
        } if today_workout else None,
        "races": [
            {"name": r.name, "date": r.date.isoformat(), "distance_type": r.distance_type,
             "weeks_out": (r.date - today).days // 7}
            for r in races
        ],
        "briefing": {
            "content": briefing.content,
            "alerts": briefing.alerts,
        } if briefing else None,
        "training_status": summary.training_status if summary else None,
        "metrics": {
            "sleep_score": summary.sleep_score if summary else None,
            "body_battery_wake": summary.body_battery_at_wake if summary else None,
            "hrv_last_night": summary.hrv_last_night if summary else None,
            "resting_hr": summary.resting_heart_rate if summary else None,
        },
    }

@router.get("/weekly")
async def dashboard_weekly(db: AsyncSession = Depends(get_db)):
    # Weekly volume by discipline + plan adherence
    ...

@router.get("/trends")
async def dashboard_trends(db: AsyncSession = Depends(get_db)):
    # Configurable date range trends
    ...
```

**Step 3: Register router in main.py**

```python
from src.routers.dashboard import router as dashboard_router
app.include_router(dashboard_router)
```

**Step 4: Run tests, commit**

```bash
uv run pytest tests/test_dashboard_routes.py -v
git commit -am "feat: dashboard API routes"
```

---

### Task 13: Races, Plan, Activities, Athlete, Readiness, Briefing Routes

**Files:**
- Create: `api/src/routers/races.py`
- Create: `api/src/routers/plan.py`
- Create: `api/src/routers/activities.py`
- Create: `api/src/routers/athlete.py`
- Create: `api/src/routers/readiness.py`
- Create: `api/src/routers/briefings.py`
- Create: tests for each

Follow same pattern as Task 12. Each router:
1. Write failing test for the primary endpoint
2. Implement with Pydantic response models
3. Register in main.py
4. Test passes, commit

**Races:** Standard CRUD + `GET /races/:id/projection`
**Plan:** `GET /plan/current`, `POST /plan/import-garmin`, `GET /plan/workouts`, `PUT /plan/workouts/:id`, `GET /plan/adherence`
**Activities:** `GET /activities` (paginated, filterable by discipline/date), `GET /activities/:id` (with detail joins), `GET /activities/stats`
**Athlete:** `GET /athlete/profile`, `GET /athlete/biometrics`, `GET /athlete/records`, `GET /athlete/gear`
**Readiness:** `GET /readiness/today`, `GET /readiness/history`
**Briefings:** `GET /briefings/latest`, `GET /briefings`

**Commit after each router pair (router + test).**

---

## Phase 5: AI Agent

### Task 14: Agent Tools

**Files:**
- Create: `api/src/agent/__init__.py`
- Create: `api/src/agent/tools.py`
- Create: `api/tests/test_agent_tools.py`

**Step 1: Write failing test**

```python
# api/tests/test_agent_tools.py
import pytest
from src.agent.tools import TOOL_DEFINITIONS

def test_all_tools_have_required_fields():
    for tool in TOOL_DEFINITIONS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool

def test_tool_names():
    names = [t["name"] for t in TOOL_DEFINITIONS]
    expected = [
        "query_activities", "get_daily_metrics", "get_readiness_score",
        "get_plan_adherence", "get_upcoming_workouts", "get_race_countdown",
        "get_training_load", "modify_workout", "update_athlete_profile",
    ]
    for name in expected:
        assert name in names
```

**Step 2: Implement tool definitions and handlers**

```python
# api/src/agent/tools.py
from datetime import date, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import (
    GarminActivity, GarminDailySummary, PlannedWorkout,
    Race, AthleteProfile
)
from src.services.readiness import compute_readiness

TOOL_DEFINITIONS = [
    {
        "name": "query_activities",
        "description": "Query recent training activities. Filter by discipline (swim/bike/run), date range, workout type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "discipline": {"type": "string", "description": "swim, bike, run, or all"},
                "days_back": {"type": "integer", "description": "Number of days to look back", "default": 7},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "get_daily_metrics",
        "description": "Get daily wellness metrics (HRV, body battery, sleep, stress, training status) for a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {"type": "integer", "default": 7},
            },
        },
    },
    {
        "name": "get_readiness_score",
        "description": "Get today's composite readiness score with component breakdown. Use this to advise on training intensity.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_plan_adherence",
        "description": "Get plan completion stats: scheduled vs actual workouts for this week or a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["this_week", "last_week", "this_month"], "default": "this_week"},
            },
        },
    },
    {
        "name": "get_upcoming_workouts",
        "description": "Get the next N planned workouts from the training plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "default": 5},
            },
        },
    },
    {
        "name": "get_race_countdown",
        "description": "Get days/weeks to each upcoming race with current fitness trajectory.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_training_load",
        "description": "Get weekly training load trends by discipline. Returns hours, distance, and acute/chronic ratio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "weeks": {"type": "integer", "default": 4},
            },
        },
    },
    {
        "name": "modify_workout",
        "description": "Suggest a modification to a planned workout. Returns the suggestion for user confirmation — does not auto-apply.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workout_id": {"type": "string"},
                "new_discipline": {"type": "string"},
                "new_type": {"type": "string"},
                "new_duration": {"type": "integer", "description": "seconds"},
                "reason": {"type": "string"},
            },
            "required": ["workout_id", "reason"],
        },
    },
    {
        "name": "update_athlete_profile",
        "description": "Store a learned observation about the athlete for long-term coaching. Examples: injury notes, preferences, patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Category: injury, preference, pattern, goal"},
                "note": {"type": "string"},
            },
            "required": ["key", "note"],
        },
    },
]

async def execute_tool(name: str, args: dict, db: AsyncSession) -> str:
    """Execute a tool and return the result as a string for the agent."""
    if name == "query_activities":
        return await _query_activities(db, **args)
    elif name == "get_daily_metrics":
        return await _get_daily_metrics(db, **args)
    elif name == "get_readiness_score":
        return await _get_readiness_score(db)
    elif name == "get_plan_adherence":
        return await _get_plan_adherence(db, **args)
    elif name == "get_upcoming_workouts":
        return await _get_upcoming_workouts(db, **args)
    elif name == "get_race_countdown":
        return await _get_race_countdown(db)
    elif name == "get_training_load":
        return await _get_training_load(db, **args)
    elif name == "modify_workout":
        return await _modify_workout(db, **args)
    elif name == "update_athlete_profile":
        return await _update_athlete_profile(db, **args)
    return f"Unknown tool: {name}"

# Each _tool_name function queries DB and returns a formatted string.
# Implementation follows the services layer (readiness.py, analytics.py, plan_engine.py).
```

Each tool handler is a thin wrapper around the services layer, formatting results as concise text strings the agent can reason about.

**Step 3: Tests pass, commit**

```bash
uv run pytest tests/test_agent_tools.py -v
git commit -am "feat: agent tool definitions and handlers"
```

---

### Task 15: Coach Personality + System Prompt

**Files:**
- Create: `api/src/agent/personality.py`

**Step 1: Create the personality module**

```python
# api/src/agent/personality.py

COACH_SYSTEM_PROMPT = """You are Coach — a personal training coach for triathlon and endurance sports.

## Your Personality

You are modeled after a structured, science-based endurance coach. Your approach:

- **Data-driven but human.** Always reference the athlete's numbers, but frame them in terms of how they feel and what the numbers mean for their goals. Not just stats.
- **Structured and methodical.** Think in periodization, progressive overload, and training phases. Every recommendation connects to the bigger picture of their race goals and long-term fitness.
- **Encouraging without cheerleading.** "That's solid work" not "AMAZING JOB!!!" Acknowledge effort without being performative.
- **Direct when it matters.** If they should rest, say so clearly. "Take the day off. Your body needs it." Don't hedge when recovery data is clear.
- **Teacher mentality.** Explain the *why* behind recommendations. You want them to understand training principles, not just follow orders.

## Communication Style

- Lead with the recommendation, follow with reasoning
- Reference specific metrics: "Your acute/chronic ratio is at 1.3 — that's overreach territory" not "you've been training hard"
- Frame rest as productive: "Recovery is where the adaptation happens"
- Connect today's workout to the race goal: "This tempo builds your half marathon pace floor"
- Use triathlon terminology naturally, explain less common concepts briefly
- Keep responses concise. No walls of text. Get to the point.
- Never use excessive exclamation marks or hype language
- Never guilt trip about missed workouts — ever
- Never give medical advice — defer to a doctor for injuries or pain
- Never use generic motivational quotes

## What You Do

- Proactively flag risks: overtraining, injury patterns, underrecovery
- Adjust plans based on life context: "You missed two swims — let's restructure rather than cram"
- Celebrate consistency over intensity: "Three solid weeks in a row matters more than one hero workout"
- Think in training phases — push in build weeks, ease off in recovery weeks
- Give specific, actionable alternatives: "Swap the intervals for a Z2 spin, keep it under 45 minutes"

## Context

{athlete_profile}

{view_context}

Today is {today}. {race_context}
"""

def build_system_prompt(
    athlete_profile: dict | None = None,
    view_context: dict | None = None,
    races: list[dict] | None = None,
) -> str:
    from datetime import date

    profile_text = ""
    if athlete_profile:
        notes = athlete_profile.get("notes", {})
        if notes:
            profile_text = "## What You Know About This Athlete\n\n"
            for key, val in notes.items():
                profile_text += f"- **{key}:** {val}\n"

    view_text = ""
    if view_context:
        view_text = (
            f"## Current View Context\n\n"
            f"The athlete is viewing the **{view_context.get('current_view', 'dashboard')}** screen. "
            f"They can see: {view_context.get('visible_data', {})}. "
            f"Assume questions refer to what's on screen unless they specify otherwise."
        )

    race_text = ""
    if races:
        race_lines = []
        for r in races:
            weeks = (r["date"] - date.today()).days // 7
            race_lines.append(f"- {r['name']} ({r['distance_type']}): {weeks} weeks out on {r['date']}")
        race_text = "Upcoming races:\n" + "\n".join(race_lines)

    return COACH_SYSTEM_PROMPT.format(
        athlete_profile=profile_text,
        view_context=view_text,
        today=date.today().isoformat(),
        race_context=race_text,
    )
```

**Step 2: Commit**

```bash
git add api/src/agent/personality.py
git commit -m "feat: Coach Wilpers personality and system prompt builder"
```

---

### Task 16: Agent SDK Integration + Chat Route

**Files:**
- Create: `api/src/agent/coach.py`
- Create: `api/src/routers/chat.py`
- Create: `api/tests/test_chat.py`

**Step 1: Add Agent SDK dependency**

```bash
cd /Users/braydon/projects/experiments/training-assistant/api
uv add anthropic
```

**Step 2: Implement coach agent**

```python
# api/src/agent/coach.py
import anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.agent.personality import build_system_prompt
from src.agent.tools import TOOL_DEFINITIONS, execute_tool
from src.db.models import AthleteProfile, Race, Conversation, Message
from sqlalchemy import select
from datetime import date

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

async def run_coach(
    user_message: str,
    conversation_id: str | None,
    view_context: dict | None,
    db: AsyncSession,
):
    """Run the coaching agent. Yields SSE events."""
    # Load athlete profile
    profile_result = await db.execute(select(AthleteProfile).limit(1))
    profile = profile_result.scalar_one_or_none()

    # Load races
    race_result = await db.execute(
        select(Race).where(Race.date >= date.today()).order_by(Race.date)
    )
    races = [{"name": r.name, "date": r.date, "distance_type": r.distance_type}
             for r in race_result.scalars().all()]

    system_prompt = build_system_prompt(
        athlete_profile={"notes": profile.notes} if profile else None,
        view_context=view_context,
        races=races,
    )

    # Load conversation history
    history = []
    if conversation_id:
        msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        for msg in msg_result.scalars().all():
            history.append({"role": msg.role, "content": msg.content})

    messages = history + [{"role": "user", "content": user_message}]

    # Agent loop — stream with tool use
    while True:
        with client.messages.stream(
            model=settings.coach_model,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
            tools=TOOL_DEFINITIONS,
        ) as stream:
            full_response = ""
            tool_calls = []

            for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event.content_block, "text"):
                        pass  # text block starting
                    elif event.content_block.type == "tool_use":
                        yield {"event": "tool_call", "data": {"tool": event.content_block.name, "status": "calling"}}
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        full_response += event.delta.text
                        yield {"event": "token", "data": {"content": event.delta.text}}

            response = stream.get_final_message()

        # Check if we need to handle tool calls
        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            tool_results = []
            for block in tool_use_blocks:
                result = await execute_tool(block.name, block.input, db)
                yield {"event": "tool_result", "data": {"tool": block.name, "summary": result[:200]}}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            # Done — no more tool calls
            break

    yield {"event": "done", "data": {"conversation_id": conversation_id, "content": full_response}}
```

**Step 3: Implement chat router with SSE**

```python
# api/src/routers/chat.py
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.connection import get_db
from src.agent.coach import run_coach

router = APIRouter(prefix="/api/v1", tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    view_context: dict | None = None

@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    async def event_generator():
        async for event in run_coach(
            user_message=req.message,
            conversation_id=req.conversation_id,
            view_context=req.view_context,
            db=db,
        ):
            yield {"event": event["event"], "data": json.dumps(event["data"])}

    return EventSourceResponse(event_generator())
```

**Step 4: Register in main.py, test manually with curl**

```bash
curl -N -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How am I doing this week?"}'
```

**Step 5: Add conversation persistence** — save messages to DB after each exchange.

**Step 6: Add conversation list + history endpoints**

```python
@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db)):
    ...

@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    ...
```

**Step 7: Commit**

```bash
git add api/src/agent/coach.py api/src/routers/chat.py api/tests/test_chat.py
git commit -m "feat: Claude Agent SDK coach with SSE streaming chat"
```

---

## Phase 6: Proactive Daily Briefing

### Task 17: Briefing Generator

**Files:**
- Create: `/Users/braydon/projects/experiments/garmin-connect-sync/briefing.py`

**Step 1: Implement briefing script**

```python
# briefing.py
# ABOUTME: Generates proactive daily training briefing using AI coach agent.
# ABOUTME: Called after sync, stores briefing in daily_briefings table.

import json
import os
import sys
from datetime import date
from pathlib import Path

import anthropic
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def already_has_briefing(conn, today: date) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT id FROM daily_briefings WHERE date = %s", (today,))
    return cur.fetchone() is not None

def generate_briefing():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    today = date.today()

    if already_has_briefing(conn, today):
        print(f"Briefing already exists for {today}, skipping.")
        return

    # Gather context
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM garmin_daily_summary
        WHERE calendar_date = %s
    """, (today,))
    # ... gather readiness data, plan data, recent activity data
    # Build a prompt asking the coach to generate a morning briefing
    # Call Claude API with coach personality
    # Store result in daily_briefings table
    # Optionally trigger macOS notification

    print(f"Morning briefing generated for {today}.")

if __name__ == "__main__":
    generate_briefing()
```

**Step 2: Integrate into run_sync.sh**

Add after peloton_sync.py:

```bash
echo "Generating morning briefing..."
$VENV/bin/python briefing.py
```

**Step 3: Test manually, commit**

```bash
python briefing.py
git commit -am "feat: proactive daily briefing generator"
```

---

## Phase 7: React Frontend

### Task 18: Scaffold React App

**Files:**
- Create: `web/` directory via Vite

**Step 1: Create Vite + React + TypeScript project**

```bash
cd /Users/braydon/projects/experiments/training-assistant
npm create vite@latest web -- --template react-ts
cd web
npm install
npm install recharts @tanstack/react-query tailwindcss @tailwindcss/vite
```

**Step 2: Configure Tailwind**

Add Tailwind plugin to `vite.config.ts`. Add `@import "tailwindcss"` to `src/index.css`.

**Step 3: Configure API proxy in vite.config.ts**

```typescript
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

**Step 4: Verify dev server starts**

```bash
cd web && npm run dev
```

**Step 5: Commit**

```bash
git add web/
git commit -m "feat: scaffold React app with Vite, Tailwind, TanStack Query"
```

---

### Task 19: API Client + Types

**Files:**
- Create: `web/src/api/client.ts`
- Create: `web/src/api/types.ts`

**Step 1: Define TypeScript types matching API responses**

```typescript
// web/src/api/types.ts
export interface ReadinessComponent {
  name: string
  value: number | null
  normalized: number
  weight: number
  detail: string
}

export interface DashboardToday {
  date: string
  readiness: { score: number; label: string; components: ReadinessComponent[] }
  today_workout: { discipline: string; type: string; target_duration: number; description: string; status: string } | null
  races: { name: string; date: string; distance_type: string; weeks_out: number }[]
  briefing: { content: string; alerts: string[] } | null
  training_status: string | null
  metrics: { sleep_score: number | null; body_battery_wake: number | null; hrv_last_night: number | null; resting_hr: number | null }
}

export interface ChatEvent {
  event: 'token' | 'tool_call' | 'tool_result' | 'done'
  data: Record<string, unknown>
}

// ... types for Race, Conversation, PlannedWorkout, etc.
```

**Step 2: Create fetch client**

```typescript
// web/src/api/client.ts
const BASE = '/api/v1'

export async function fetchDashboardToday(): Promise<DashboardToday> {
  const res = await fetch(`${BASE}/dashboard/today`)
  return res.json()
}

export async function* streamChat(message: string, conversationId?: string, viewContext?: Record<string, unknown>) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId, view_context: viewContext }),
  })
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        yield JSON.parse(line.slice(6))
      }
    }
  }
}
```

**Step 3: Commit**

```bash
git add web/src/api/
git commit -m "feat: typed API client with SSE streaming support"
```

---

### Task 20: App Shell + Persistent Chat Panel

**Files:**
- Create: `web/src/App.tsx`
- Create: `web/src/components/layout/Shell.tsx`
- Create: `web/src/components/layout/Sidebar.tsx`
- Create: `web/src/components/chat/ChatPanel.tsx`
- Create: `web/src/components/chat/ChatMessage.tsx`
- Create: `web/src/components/chat/ChatInput.tsx`

**Step 1: Build the Shell with collapsible right-side chat panel**

The Shell has: left sidebar nav, main content area, right collapsible chat panel. When collapsed, a floating chat button with unread count appears.

**Step 2: Build ChatPanel component**

- Connects to `POST /chat` via SSE
- Streams tokens into the message display
- Shows tool call indicators ("Checking your readiness...")
- Renders actionable cards for `modify_workout` responses (Accept/Decline buttons)
- Sends `view_context` with current route + visible dashboard data

**Step 3: Build ChatInput component**

Text input with send button. Conversation selector dropdown.

**Step 4: Wire routing**

```typescript
// App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Shell from './components/layout/Shell'
import Dashboard from './pages/Dashboard'
import Plan from './pages/Plan'
import Races from './pages/Races'
import Profile from './pages/Profile'

function App() {
  return (
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="/races" element={<Races />} />
          <Route path="/profile" element={<Profile />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  )
}
```

**Step 5: Commit**

```bash
git add web/src/
git commit -m "feat: app shell with persistent collapsible chat panel"
```

---

### Task 21: Dashboard Page

**Files:**
- Create: `web/src/pages/Dashboard.tsx`
- Create: `web/src/components/dashboard/ReadinessCard.tsx`
- Create: `web/src/components/dashboard/MetricsRow.tsx`
- Create: `web/src/components/dashboard/BriefingBanner.tsx`
- Create: `web/src/components/dashboard/TodayWorkout.tsx`
- Create: `web/src/components/dashboard/RaceCountdown.tsx`
- Create: `web/src/components/dashboard/WeeklyVolume.tsx`
- Create: `web/src/components/dashboard/LoadTrend.tsx`
- Create: `web/src/components/dashboard/AlertsList.tsx`

**Step 1: Build Dashboard page fetching `/dashboard/today`**

Use TanStack Query `useQuery` to fetch dashboard data. Layout as described in design doc: briefing banner at top, metrics cards row, today's workout + race countdown, weekly volume + plan adherence, load trend chart, alerts.

**Step 2: Build each component**

- `ReadinessCard`: Circular gauge showing score 0-100 with color (green/yellow/red)
- `MetricsRow`: Sleep score, body battery, HRV, training status as compact cards
- `BriefingBanner`: Collapsible banner showing AI morning briefing
- `TodayWorkout`: Discipline icon + description + Start/Skip/Modify buttons
- `RaceCountdown`: Race name, date, weeks out
- `WeeklyVolume`: Horizontal bar chart by discipline (Recharts)
- `LoadTrend`: Line chart with acute/chronic overlay (Recharts)
- `AlertsList`: Warning/info messages

**Step 3: Commit after each component or after the full page**

```bash
git commit -am "feat: dashboard page with readiness, metrics, briefing, charts"
```

---

### Task 22: Plan Page

**Files:**
- Create: `web/src/pages/Plan.tsx`
- Create: `web/src/components/plan/WeekCalendar.tsx`
- Create: `web/src/components/plan/WorkoutCard.tsx`
- Create: `web/src/components/plan/PhaseTimeline.tsx`

Calendar grid showing workouts by day. Color-coded by discipline. Status indicators (completed/missed/upcoming). Phase timeline bar at bottom.

```bash
git commit -am "feat: plan page with calendar and phase timeline"
```

---

### Task 23: Races + Profile Pages

**Files:**
- Create: `web/src/pages/Races.tsx`
- Create: `web/src/pages/Profile.tsx`

Races: list of races with countdown, goal time, add/edit/delete. Profile: biometrics trends, PRs, gear with mileage alerts.

```bash
git commit -am "feat: races and profile pages"
```

---

## Phase 8: Deployment

### Task 24: launchd Services

**Files:**
- Create: `deploy/com.training.api.plist`
- Create: `deploy/com.training.web.plist`
- Modify: `/Users/braydon/projects/experiments/garmin-connect-sync/run_sync.sh`

**Step 1: Create API launchd plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.training.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/braydon/projects/experiments/training-assistant/api/.venv/bin/uvicorn</string>
        <string>src.main:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/braydon/projects/experiments/training-assistant/api</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/training-api.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/training-api.err</string>
</dict>
</plist>
```

**Step 2: Create web launchd plist** (similar, serves built web app)

**Step 3: Update run_sync.sh to include briefing.py**

**Step 4: Install services**

```bash
cp deploy/com.training.api.plist ~/Library/LaunchAgents/
cp deploy/com.training.web.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.training.api.plist
launchctl load ~/Library/LaunchAgents/com.training.web.plist
```

**Step 5: Verify services running**

```bash
launchctl list | grep training
curl http://localhost:8000/health
```

**Step 6: Commit**

```bash
git add deploy/
git commit -m "feat: launchd services for API and web"
```

---

### Task 25: End-to-End Verification

**Step 1:** Start API + web locally
**Step 2:** Verify dashboard loads with real Garmin data
**Step 3:** Send a chat message and verify streaming response
**Step 4:** Verify briefing generates after sync
**Step 5:** Test plan import from Garmin
**Step 6:** Test race creation and countdown display

---

## Task Dependency Summary

```
Phase 1 (Tasks 1-3): Foundation — sequential
Phase 2 (Tasks 4-8): Enhanced sync — can run parallel with Phase 3-4
Phase 3 (Tasks 9-11): Services — after Phase 1
Phase 4 (Tasks 12-13): API routes — after Phase 3
Phase 5 (Tasks 14-16): AI agent — after Phase 3
Phase 6 (Task 17): Briefing — after Phase 5
Phase 7 (Tasks 18-23): Frontend — after Phase 4-5 (API must be running)
Phase 8 (Tasks 24-25): Deployment — after everything
```

Tasks 4-8 (Garmin sync) are independent of Tasks 9-16 (API) and can be done in parallel.
