# Training Assistant — Design Document

**Date:** 2026-02-18
**Status:** Approved
**Author:** Braydon + Claude

## Vision

A long-term personal training coach that learns about you over time. Current focus is half iron man training with multiple scheduled races, but the system grows into a comprehensive fitness coach. API-first architecture — the API is the product, frontends are consumers.

## Architecture: Python API + React App (Monorepo)

```
training-assistant/
├── api/                          # Python FastAPI — all business logic, AI agent, data
│   ├── src/
│   │   ├── main.py               # FastAPI app, CORS, middleware
│   │   ├── config.py             # Settings (DB URL, Claude API key, etc.)
│   │   ├── db/
│   │   │   ├── connection.py     # Async PostgreSQL pool
│   │   │   ├── models.py         # SQLAlchemy/Pydantic models
│   │   │   └── migrations/       # Alembic migrations
│   │   ├── routers/
│   │   │   ├── chat.py           # POST /chat (streaming SSE), GET /conversations
│   │   │   ├── plan.py           # CRUD for training plan + schedule
│   │   │   ├── dashboard.py      # GET endpoints for dashboard data
│   │   │   └── races.py          # CRUD for race events
│   │   ├── agent/
│   │   │   ├── coach.py          # Claude Agent SDK training coach
│   │   │   ├── personality.py    # Coach Wilpers persona definition
│   │   │   └── tools/            # Agent tools (query DB, check plan, etc.)
│   │   └── services/
│   │       ├── readiness.py      # Daily readiness scoring logic
│   │       ├── plan_engine.py    # Plan adherence, adaptation logic
│   │       └── analytics.py      # Load calculations, trends, projections
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── web/                          # React Vite — dashboard + chat UI
│   ├── src/
│   │   ├── components/
│   │   │   ├── dashboard/        # Charts, metrics cards, race countdown
│   │   │   ├── chat/             # Persistent chat panel (all views)
│   │   │   └── plan/             # Plan view, calendar, adherence
│   │   ├── hooks/                # Data fetching hooks (TanStack Query)
│   │   ├── api/                  # API client (typed, from OpenAPI)
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── openapi.yaml                  # Generated from FastAPI
```

## Data Layer

### Existing Tables (from garmin-connect-sync, untouched)

- `garmin_activities` — per-activity data (distance, duration, HR, power, swim metrics, training effect, raw JSON)
- `garmin_daily_summary` — daily metrics (training status, load, VO2 max, readiness, body battery, HRV, sleep, race predictions, stress, RHR)

### New Tables

```sql
-- Athlete biometrics (one row per date, updated daily)
athlete_biometrics (
  id, date, weight_kg, body_fat_pct, muscle_mass_kg, bmi,
  fitness_age, actual_age, lactate_threshold_hr, lactate_threshold_pace,
  cycling_ftp, vo2_max_detailed jsonb,
  raw_data jsonb, synced_at
)

-- Races
races (
  id, name, date, distance_type, goal_time, notes, created_at
)

-- Training plans
training_plan (
  id, race_id nullable, name, source (garmin/custom/ai),
  start_date, end_date, created_at
)

-- Planned workouts
planned_workouts (
  id, plan_id, date, discipline (swim/bike/run/strength/rest),
  workout_type (easy/tempo/intervals/long/brick/etc.),
  target_duration, target_distance, target_hr_zone,
  description, completed_activity_id FK -> garmin_activities,
  status (upcoming/completed/missed/skipped/modified)
)

-- Garmin training plan imports
garmin_training_plans (
  id, garmin_plan_id, name, plan_type, start_date, end_date,
  raw_data jsonb, synced_at
)

-- Garmin planned/scheduled workouts
garmin_planned_workouts (
  id, garmin_workout_id, plan_id, date, discipline,
  workout_type, description, target_data jsonb,
  raw_data jsonb, synced_at
)

-- Activity detail enrichment
activity_details (
  id, garmin_activity_id FK, splits jsonb,
  hr_zones jsonb, weather jsonb, gear_id,
  raw_data jsonb, synced_at
)

-- Gear tracking
gear (
  id, garmin_gear_uuid, name, gear_type, brand, model,
  date_begin, max_distance_km, total_distance_km,
  total_activities, raw_data jsonb, synced_at
)

-- Personal records
personal_records (
  id, record_type, activity_type, value, activity_id,
  recorded_at, raw_data jsonb, synced_at
)

-- Daily AI briefings
daily_briefings (
  id, date, content markdown, readiness_summary,
  workout_recommendation, alerts jsonb,
  raw_agent_response jsonb, created_at
)

-- Chat conversations
conversations (
  id, title, created_at, updated_at
)

-- Chat messages
messages (
  id, conversation_id, role (user/assistant), content,
  tool_calls jsonb, created_at
)

-- Long-term athlete memory
athlete_profile (
  id, notes jsonb, goals, injury_history, preferences, updated_at
)
```

### Expanded garmin_daily_summary columns

```sql
ALTER garmin_daily_summary ADD:
  steps, total_calories, active_calories,
  active_minutes_moderate, active_minutes_vigorous,
  respiration_avg, spo2_avg, spo2_low,
  morning_readiness_score, daily_distance_meters,
  body_battery_events jsonb, heart_rate_zones jsonb
```

## Comprehensive Garmin Data Sync

### Tier 1: Athlete Profile (daily)

| Method | Data |
|--------|------|
| `get_user_profile()` | Age, weight, display name, units |
| `get_fitnessage_data()` | Fitness age |
| `get_body_composition()` | Weight, BMI, body fat %, muscle mass |
| `get_max_metrics()` | VO2 max (detailed) |
| `get_lactate_threshold()` | LT heart rate + pace |
| `get_cycling_ftp()` | Functional threshold power |
| `get_personal_record()` | PRs across disciplines |
| `get_goals()` | Active Garmin goals |

### Tier 2: Daily Wellness (with existing daily job)

| Method | Data |
|--------|------|
| `get_user_summary()` | Steps, calories, active minutes, distance |
| `get_respiration_data()` | Breathing rate trends |
| `get_spo2_data()` | Blood oxygen |
| `get_intensity_minutes_data()` | Moderate + vigorous minutes |
| `get_heart_rates()` | Intraday HR curve |
| `get_body_battery_events()` | What drained/charged battery |
| `get_morning_training_readiness()` | Morning-specific readiness |
| `get_weekly_stress()` | Stress trends |

### Tier 3: Training Plan + Workouts (with existing job)

| Method | Data |
|--------|------|
| `get_training_plans()` | Garmin training plans |
| `get_training_plan_by_id()` | Plan details + phases |
| `get_workouts()` | Saved workout library |
| `get_scheduled_workout_by_id()` | Calendar workouts |

### Tier 4: Activity Detail (per new activity)

| Method | Data |
|--------|------|
| `get_activity_splits()` | Lap/split data |
| `get_activity_hr_in_timezones()` | HR zone time |
| `get_activity_weather()` | Weather conditions |
| `get_activity_details()` | Full chart/polyline data |
| `get_activity_gear()` | Shoes/bike used |

### Tier 5: Gear (weekly)

| Method | Data |
|--------|------|
| `get_gear()` | All equipment |
| `get_gear_stats()` | Usage per gear item |

### Not Syncing (YAGNI)

Women's health, blood pressure, hydration logging, badges/challenges, device settings/alarms, GraphQL/low-level.

## AI Agent (Coach)

### Architecture

Claude Agent SDK agent running server-side in the API. Frontends interact via `POST /chat` (SSE streaming).

### Agent Tools

| Tool | Purpose |
|------|---------|
| `query_activities` | Fetch recent activities by discipline, date range, type |
| `get_daily_metrics` | HRV, body battery, sleep, stress for a date range |
| `get_readiness_score` | Today's computed readiness (composite) |
| `get_plan_adherence` | Scheduled vs. actual for current week/month |
| `get_upcoming_workouts` | Next N planned workouts |
| `get_race_countdown` | Days/weeks to each race + fitness trajectory |
| `get_training_load` | Weekly/monthly load trends by discipline |
| `modify_workout` | Suggest a plan adjustment (requires user confirmation) |
| `update_athlete_profile` | Store learned info (injuries, preferences, goals) |

### Personality: Coach Wilpers

**Core traits:**
- Data-driven but human — references numbers, frames them in how you feel and what they mean
- Structured and methodical — periodization, progressive overload, training phases. Every recommendation connects to the bigger picture
- Encouraging without cheerleading — "That's solid work" not "AMAZING JOB!!!"
- Direct when it matters — doesn't hedge when recovery data says rest
- Teacher mentality — explains the why

**Communication patterns:**
- Leads with the recommendation, follows with reasoning
- References specific metrics: "Your acute/chronic ratio is at 1.3" not "you've been training hard"
- Frames rest as productive: "Recovery is where the adaptation happens"
- Connects today's workout to the race goal
- Uses triathlon terminology naturally, explains less common concepts

**Does:**
- Proactively flags risks (overtraining, injury patterns, underrecovery)
- Adjusts plans based on life context
- Celebrates consistency over intensity
- Thinks in training phases
- Gives specific, actionable alternatives

**Does not:**
- Guilt trip about missed workouts
- Use excessive exclamation marks or hype language
- Give medical advice
- Recommend anything contradicting recovery data without clear explanation
- Use generic motivational quotes

**Example — morning briefing:**
> Good morning. Quick snapshot — sleep was solid at 7.4 hours, HRV is back up to 48 after dipping earlier this week, body battery charged to 72. You're in good shape for today's bike intervals. Focus on holding your target power in the 3rd and 4th intervals — that's where the real work happens. The first two are just getting dialed in.

**Example — missed workout:**
> You missed Wednesday's swim — no stress. Looking at your week, you've got solid run and bike volume. I'd add 15 minutes to Saturday's swim to make up the distance, rather than trying to squeeze in an extra session. Consistency over perfection.

**Example — overreaching:**
> Let's talk about this week honestly. Your HRV has dropped three days in a row, body battery hasn't cracked 50 at wake, and your acute load is 1.4x your chronic — that's above the threshold I like to see. I'm pulling tomorrow's intervals. Do a Z1 recovery spin, 30 minutes max. We'll reassess Thursday. The fitness isn't going anywhere — pushing through this is how injuries happen.

### Memory / Learning

The `athlete_profile` table is the agent's long-term memory. Over conversations, it updates notes like:
- "Tends to overtrain on bike, undertrain on swim"
- "Left knee issues — avoid back-to-back run days"
- "Prefers morning workouts, races better when tapered 2 weeks"

Injected into every conversation's system prompt.

## Proactive Daily Briefing

### launchd Flow

```
run_sync.sh (every 6h, existing):
  1. sync.py --comprehensive     # all garmin data (tiers 1-3)
  2. peloton_sync.py             # peloton bridge
  3. briefing.py                 # AI briefing (first run of day only)
     -> calls the agent with "Generate morning briefing"
     -> stores in daily_briefings table
     -> macOS notification: "Your training briefing is ready"
```

`briefing.py` checks if a briefing exists for today — only generates one.

Activity detail enrichment (tier 4) runs per-activity on sync for new activities only. Gear stats (tier 5) refresh weekly.

## API Design

```
Base: http://localhost:8000/api/v1

Chat:
  POST   /chat                    # SSE streaming
  GET    /conversations
  GET    /conversations/:id
  DELETE /conversations/:id

Dashboard:
  GET    /dashboard/today         # Snapshot: readiness, plan, metrics
  GET    /dashboard/weekly        # Weekly: volume, load, adherence
  GET    /dashboard/trends        # Configurable trends

Briefing:
  GET    /briefings/latest
  GET    /briefings

Races:
  GET    /races
  POST   /races
  PUT    /races/:id
  DELETE /races/:id
  GET    /races/:id/projection

Plan:
  GET    /plan/current
  POST   /plan/import-garmin
  GET    /plan/workouts
  PUT    /plan/workouts/:id
  GET    /plan/adherence

Athlete:
  GET    /athlete/profile
  GET    /athlete/biometrics
  GET    /athlete/records
  GET    /athlete/gear

Activities:
  GET    /activities
  GET    /activities/:id
  GET    /activities/stats

Readiness:
  GET    /readiness/today
  GET    /readiness/history
```

### Chat Streaming Events

```
event: token        -> {"content": "I'd recommend"}
event: tool_call    -> {"tool": "get_readiness_score", "status": "calling"}
event: tool_result  -> {"tool": "get_readiness_score", "summary": "Score: 72"}
event: done         -> {"conversation_id": "abc", "message_id": "msg"}
```

### Chat Context Awareness

Every chat message includes `view_context`:

```json
{
  "message": "Is this too much?",
  "conversation_id": "abc123",
  "view_context": {
    "current_view": "plan",
    "visible_data": {
      "week": "2026-02-17",
      "planned_hours": 10.5,
      "workouts": ["long run", "bike intervals", "brick", "swim tempo"]
    }
  }
}
```

Agent system prompt includes: "The user is currently viewing the {view} screen. They can see: {visible_data}. Assume they're referring to what's on screen unless they specify otherwise."

## Frontend: React Dashboard + Persistent Chat

### Layout

Persistent collapsible chat panel on the right side of every view. Collapses to a floating button with unread count. Context-aware — sends current view data with messages.

### Views

- **Dashboard (home):** Daily briefing, readiness/sleep/body battery/training status cards, today's workout, race countdowns, weekly volume bars, plan adherence %, load trend chart, alerts
- **Plan:** Calendar view with workout cards, completion status, phase timeline, import from Garmin
- **Races:** Race list with countdowns, goal times, fitness projections
- **Profile:** Athlete info, biometrics trends, PRs, gear with mileage

### Tech Stack

- Vite + React + TypeScript
- Recharts for charts
- TanStack Query for data fetching + SSE
- Tailwind CSS
- OpenAPI-generated typed API client

### Frontend Principles

- No business logic — all computation in the API
- No direct DB access
- No AI calls — chat goes through API

## Infrastructure

### Local Development

```bash
# API
cd api && uvicorn src.main:app --reload --port 8000

# Web
cd web && npm run dev
```

Reuses existing PostgreSQL (same `assistant` database as garmin-connect-sync).

### Production (Local Machine) — launchd Services

| Service | Schedule | Purpose |
|---------|----------|---------|
| `com.garmin.sync.plist` | Every 6 hours (existing) | Data sync + briefing |
| `com.training.api.plist` | On login, keep alive | FastAPI server |
| `com.training.web.plist` | On login, keep alive | Static serve |

### Environment

```env
DATABASE_URL=postgresql://braydon@localhost:5432/assistant
ANTHROPIC_API_KEY=sk-ant-...
COACH_MODEL=claude-sonnet-4-6
SYNC_DAYS_BACK=3
BRIEFING_ENABLED=true
```

### Testing

- API: pytest + httpx async test client
- Agent: Mock tool responses, verify correct tool selection
- Web: Vitest + React Testing Library
- Integration: API tests against real DB with test data
