# Training Assistant

## Why I Built This

I built Training Assistant while training for a Half Ironman in June.
My schedule is unpredictable week to week, so static training plans kept breaking.

My real training data lived in multiple places, and the daily decision was still manual.
I needed an AI coach that could adapt guidance to real life, not an idealized plan.

I wanted one place that answers:

- How recovered am I today?
- What workout should I actually do today?
- Is my calendar in sync with what Garmin shows on watch/Connect?
- Are my race goals and weekly load moving in the right direction?

This project turns raw metrics into daily coaching context I can act on quickly.

## What It Does For Me

- Pulls daily readiness signals (sleep, HRV, body battery, load) into one dashboard
- Shows plan calendar plus workout detail popovers on each day
- Lets me compare planned vs completed work and spot drift early
- Provides trend analysis and coaching interpretation of the data
- Adapts day-by-day recommendations when my calendar or energy changes
- Supports on-demand Garmin refresh when I open/refresh the app
- Syncs completed Peloton workouts into Garmin so they appear in the same training history

## Why It's Valuable

- Less context switching: one app instead of bouncing between Garmin pages
- Better day-of decisions: readiness + plan + races shown together
- Fewer sync surprises: refresh endpoint helps pull latest Garmin daily data
- More consistency: plan adherence and trend views show what needs attention
- Training guidance matches my actual life constraints, not generic one-size-fits-all plans

## The Coach (Personality + Behavior)

This app includes a streaming AI coach (`/api/v1/chat`) that is intentionally
configured to act like a practical endurance coach, not a generic chatbot.

Model/runtime:

- Default model: `claude-sonnet-4-6` (`COACH_MODEL` in API config)
- Tool-use loop with live token streaming (SSE)
- Uses DB-backed tools for activities, readiness, load, races, plan adherence,
  biometrics, and active alerts
- Uses long-term PG vector memory for retrieval, while the chat panel loads
  recent history in pages (so the UI stays usable without losing memory depth)

Coaching methodology:

- Informed by Matt Wilpers-style principles: periodization, purpose-driven
  sessions, recovery as real training data, and race-specific balance
- Context checks include phase (`base/build/peak/taper/race_week`), A-race
  countdown, acute:chronic load, discipline split, recovery signals, and
  recent biometrics

Personality/tone rules:

- Direct, concise, conversational
- Numbers over vague language
- Short phone-friendly output (no markdown tables)
- No guilt for missed sessions; restructure instead
- No medical advice
- Suggest changes first, then wait for athlete confirmation before applying

Briefing behavior:

- Daily briefing is short, structured, and A-race-focused
- Separates headline, readiness summary, workout recommendation, and alerts
- Produces structured recommendation-change payloads when workout edits are warranted

## Screenshots

All screenshots below are sanitized/redacted sample views (no personal metrics,
race details, or API secrets).

![Dashboard (redacted sample)](docs/images/dashboard-redacted.png)
![Plan Calendar + Workout Details (redacted sample)](docs/images/plan-redacted.png)
![Analysis (redacted sample)](docs/images/analysis-redacted.png)

## Architecture

- `api/`: FastAPI backend with analytics, planning, briefings, and Garmin sync bridges
- `web/`: React + Vite frontend for dashboard, calendar, races, and chat
- `deploy/`: macOS LaunchAgent scripts for local service management

## Requirements

- Python 3.12+
- `uv` (API dependency management)
- Node.js 20+ and npm
- PostgreSQL

## Data Dependency Notes

The API reads Garmin tables that are not fully created by this repo's migrations:

- `garmin_activities`
- `garmin_daily_summary`
- `athlete_biometrics`

These are expected to be populated by the sibling `garmin-connect-sync` workflow
in the same `experiments/` workspace.

If Garmin sync is not configured yet, you can still run the app by disabling
Garmin refresh/writeback in `api/.env` (see `api/.env.example`).

### External Sync Pipeline (Garmin + Peloton)

`training-assistant` depends on `garmin-connect-sync` for ingestion.

- Garmin activity/recovery/calendar sync: `sync.py`
- Peloton to Garmin bridge: `peloton_sync.py`
- Scheduled combined sync runner: `run_sync.sh` (runs both)

Expected workspace layout:

- `/path/to/experiments/training-assistant`
- `/path/to/experiments/garmin-connect-sync`

First-time setup for ingestion:

```bash
cd ../garmin-connect-sync
cp .env.example .env
# Edit .env:
#   DATABASE_URL=postgresql://<db-user>:<db-pass>@localhost:5432/assistant
#   PELOTON_EMAIL=<your email>
#   PELOTON_PASSWORD=<your password>

# Authenticate Garmin and cache tokens
python3 auth.py

# Run combined Garmin + Peloton sync
./run_sync.sh
```

Install scheduled sync jobs:

```bash
cd ../garmin-connect-sync
./install.sh
```

Manual commands:

```bash
# Combined Garmin + Peloton sync
cd ../garmin-connect-sync && ./run_sync.sh

# Peloton-only sync window
cd ../garmin-connect-sync && .venv/bin/python3 peloton_sync.py --days-back 7
```

## Quick Start

1. API setup:

```bash
cd api
cp .env.example .env
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

2. Web setup (new terminal):

```bash
cd web
npm install
npm run dev -- --host 0.0.0.0 --port 4100
```

3. Open `http://127.0.0.1:4100`

The web app proxies `/api` requests to `http://127.0.0.1:8000`.

## Refresh + Garmin Sync

- Dashboard refresh endpoint: `POST /api/v1/dashboard/refresh`
- On-demand refresh pulls latest daily metrics via `garmin-connect-sync`
- Refresh cadence is controlled by `GARMIN_REFRESH_MIN_INTERVAL_SECONDS`
- This refresh endpoint is Garmin-focused; Peloton import runs via `garmin-connect-sync/run_sync.sh`

## Privacy and Secrets

- `.env` files are gitignored; use `api/.env.example` as a template
- Do not commit personal API keys or personal workout exports
- Public screenshots in this repo are intentionally redacted

## Development Commands

API smoke tests (DB-light):

```bash
cd api
uv run pytest -q tests/test_health.py tests/test_dashboard_routes.py::test_dashboard_refresh
```

Full API tests (requires populated DB/tables):

```bash
cd api
uv run pytest -q
```

Web production build:

```bash
cd web
npm run build
```

## Local Service Scripts (macOS)

- Restart services: `./deploy/restart_training_assistant.sh`
- Check status: `./deploy/status_training_assistant.sh`

## Contributing

See `CONTRIBUTING.md`.

## License

MIT (`LICENSE`).
