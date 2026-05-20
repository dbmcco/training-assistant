# Training Assistant

Personal triathlon training coach — API-first with streaming AI coach, Garmin/Peloton sync, and React dashboard.

## Architecture

- **`api/`** — FastAPI backend (Python 3.12, uv, async SQLAlchemy + asyncpg)
- **`web/`** — React + Vite + TypeScript frontend (Tailwind, TanStack Query)
- **`deploy/`** — macOS LaunchAgent service scripts
- **DB** — PostgreSQL `assistant` on localhost:5432 (shared with garmin-connect-sync)

### Ports

| Service | Port |
|---------|------|
| API (uvicorn) | 8001 |
| Web (Vite dev) | 4100 |

### Key API Directories

```
api/src/
├── agent/           # Coach agent (coach.py, personality.py, tools.py)
├── routers/         # FastAPI routes (chat, dashboard, plan, races, recommendations, ...)
├── services/        # Business logic (recommendations, assistant_plan, garmin_refresh, garmin_writeback, memory_store, plan_engine, analytics, ...)
├── db/              # SQLAlchemy models + Alembic migrations
├── config.py        # Pydantic Settings (.env loader)
└── main.py          # FastAPI app
```

### Key Service Modules

- **`recommendations.py`** — Intent/approval pipeline: `create_plan_change_intent` → athlete approval → `decide_recommendation` → Garmin writeback
- **`assistant_plan.py`** — AI-generated training plan (rolling multi-day, Garmin sync)
- **`garmin_writeback.py`** — Pushes workout changes to Garmin Connect
- **`garmin_refresh.py`** — On-demand Garmin daily data pull via garmin-connect-sync
- **`memory_store.py`** — PG vector embeddings for coach long-term memory
- **`plan_engine.py`** — Plan adherence, completion matching, stats

### Coach Agent

- Model: `claude-sonnet-4-6` (configurable via `COACH_MODEL` in .env)
- Uses raw `anthropic.AsyncAnthropic` with tool-use loop + SSE streaming
- System prompt built dynamically with athlete context (phase, load, recovery, races)
- 15+ DB-backed tools (query_activities, get_upcoming_workouts, create_plan_change_intent, build_assistant_plan, etc.)
- Long-term memory via PG vector search on conversation extracts

## Development

```bash
# API tests (138 passing)
cd api && uv run pytest -q

# API dev server
cd api && uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# Web dev server
cd web && npm run dev -- --host 0.0.0.0 --port 4100

# Web production build
cd web && npm run build
```

### launchd Services

- `com.training.api` — uvicorn on port 8001 (always running)
- `com.training.web` — Vite preview on port 4100 (always running)
- Restart: `launchctl kickstart -k gui/$(id -u)/com.training.api`

## Data Dependencies

This repo reads tables populated by sibling `garmin-connect-sync`:
- `garmin_activities`, `garmin_daily_summary`, `athlete_biometrics`
- `planned_workouts` (calendar sync writes here too)

## Key Config (.env)

- `DATABASE_URL` — async PG connection string
- `ANTHROPIC_API_KEY` — for coach agent
- `COACH_MODEL` — Claude model ID
- `PLAN_OWNERSHIP_MODE` — `garmin` (default) or `assistant`
- `GARMIN_REFRESH_*` — refresh interval and backfill window

<!-- driftdriver-claude:start -->
## Speedrift Ecosystem

**Speedrift** is the development quality system across this workspace. It combines
[Workgraph](https://github.com/graphwork/workgraph) (task spine) with
[Driftdriver](https://github.com/dbmcco/driftdriver) (drift orchestrator) to keep
code, specs, and intent in sync without hard-blocking work.

Use `/speedrift` (or `/rifts`) to invoke the full protocol skill.

### Quick Reference

```bash
# Drift-check a task (run at start + before completion)
./.workgraph/drifts check --task <id> --write-log --create-followups

# Ecosystem dashboard (40+ repos, pressure scores, action queue)
# Local:     http://127.0.0.1:8777/
# Tailscale: http://100.77.214.44:8777/

# Create tasks with current wg flags
wg add "Title" --after <dep-id> --no-place --verify "test command"

# Attractor loop — check convergence status or run convergence
driftdriver attractor status --json
driftdriver attractor run --json
```

### Execution Layer (wg + Agency)
- **Workgraph** is the task spine: dependencies, dispatch, readiness.
- **Agency** (`agency serve`, port 8000) is the agent composition engine: *who* runs a task.
  At dispatch time Agency composes an agent configuration; planforge/speedrift wrap it with
  the protocol envelope (wg-contract, drift checks, executor guidance).
- Agency is always-on launchd. If unreachable, dispatch continues with generic prompts.
- Check: `curl -s http://localhost:8000/health`

### Runtime Authority
- Workgraph is the task/dependency source of truth. `speedriftd` is the repo-local supervisor.
- Sessions default to `observe`. Do not use `wg service start` as a generic kickoff.
- Refresh state: `driftdriver --dir "$PWD" --json speedriftd status --refresh`
- Arm repo: `driftdriver --dir "$PWD" speedriftd status --set-mode supervise --lease-owner <agent> --reason "reason"`
- Disarm: `driftdriver --dir "$PWD" speedriftd status --set-mode observe --release-lease --reason "done"`

### Dark Factory
This repo is part of a dark factory managed by the **Factory Brain** — a three-tier
LLM supervisor (Haiku → Sonnet → Opus) that watches all enrolled repos via events
and heartbeats.

**What the brain does:**
- Monitors `events.jsonl` for lifecycle events (crashes, stalls, agent deaths)
- Checks dispatch-loop heartbeats for stale repos
- Issues directives: restart loops, kill daemons, spawn agents, adjust concurrency, enroll/unenroll repos
- Escalates through tiers when lower tiers can't resolve issues
- Sends Telegram alerts for significant events

**How interactive sessions coexist:**
- When you open a Claude Code session, a `session.started` event is emitted and
  interactive presence is registered automatically (via hooks).
- The brain **suppresses action directives** for repos with active interactive sessions.
- When you close the session, `session.ended` fires and the brain resumes control.
- If a session crashes without clean exit, the brain resumes after the presence
  heartbeat goes stale (~10 minutes).

**You don't need to do anything.** The hooks handle session detection automatically.
The brain backs off when you're here and resumes when you leave.

### Attractor Loop (Convergence Engine)
- Each repo declares a target attractor in `drift-policy.toml`: `onboarded` → `production-ready` → `hardened`
- The loop runs diagnose → plan → execute → re-diagnose until convergence or circuit breaker
- Circuit breakers: max 3 passes, plateau detection (2 consecutive no-improvement), task budget cap (30)
- Bundles (reusable fix templates) are matched to findings automatically; unmatched findings escalate
- Check status: `driftdriver attractor status --json`
- Run convergence: `driftdriver attractor run --json`

### What Happens Automatically
- **Drift task guard**: follow-up tasks are deduped + capped at 3 per lane per repo
- **Attractor convergence**: repos are driven toward their declared target state via the attractor loop
- **Factory brain**: watches events, restarts crashed loops, escalates persistent issues
- **Session awareness**: brain backs off when interactive sessions are active
- **Notifications**: significant findings alert via terminal/webhook/wg-notify
- **Prompt evolution**: recurring drift patterns trigger `wg evolve` to teach agents
- **Outcome learning**: resolution rates feed back into notification significance scoring
<!-- driftdriver-claude:end -->
