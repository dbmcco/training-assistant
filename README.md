# Training Assistant

Training Assistant is a two-tier app for triathlon/endurance coaching:

- `api/`: FastAPI backend with analytics, planning, briefings, and Garmin sync bridges
- `web/`: React + Vite frontend for dashboard, calendar, races, and chat
- `deploy/`: macOS LaunchAgent scripts for local service management

## Requirements

- Python 3.12+
- `uv` (for API dependency management)
- Node.js 20+ and npm
- PostgreSQL

## Important Data Dependency

The API reads Garmin tables that are not fully created by this repo's migrations:

- `garmin_activities`
- `garmin_daily_summary`
- `athlete_biometrics`

Those are expected to be populated by the sibling `garmin-connect-sync` workflow in the same `experiments/` workspace.

If you do not have Garmin sync set up yet, you can still run the app by disabling Garmin refresh/writeback in `api/.env` (see `api/.env.example`).

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

3. Open:

- `http://127.0.0.1:4100`

The web app proxies `/api` requests to `http://127.0.0.1:8000`.

## Refresh + Garmin Sync Behavior

- The dashboard can call `POST /api/v1/dashboard/refresh` on app refresh/load.
- This on-demand refresh pulls latest daily recovery metrics (sleep score, HRV, readiness) via `garmin-connect-sync`.
- Refresh cadence is controlled by `GARMIN_REFRESH_MIN_INTERVAL_SECONDS` in API env config.

## Development Commands

- API smoke tests (DB-light):

```bash
cd api
uv run pytest -q tests/test_health.py tests/test_dashboard_routes.py::test_dashboard_refresh
```

- Full API tests (requires populated DB/tables):

```bash
cd api
uv run pytest -q
```

- Web production build:

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
