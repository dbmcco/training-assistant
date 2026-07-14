# Garmin Integration Cutover Runbook

This runbook governs the migration from the legacy Garmin worker to the
Training Assistant-owned worker. It is intentionally staged: the old scheduler
must remain available until the new worker has passed the canary and soak gates.

## Pre-cutover checks

Run from the Training Assistant repository:

```bash
cd api
uv run pytest -q
uv run alembic upgrade head
uv run python scripts/verify_garmin_schema.py
plutil -lint ../deploy/com.training.garmin-sync.plist
bash -n scripts/run_garmin_sync.sh
```

The schema report must show the existing Garmin identifier counts and no missing
required tables or columns. Do not proceed if counts decrease or the migration
requests a destructive operation.

## Token-store migration

Copy the existing local token store into the Training Assistant-owned location
without printing or committing its contents:

```bash
export GARMIN_LEGACY_TOKEN_SOURCE="$HOME/.config/garmin-token-store"
mkdir -p "$HOME/.config/training-assistant"
cp -R "$GARMIN_LEGACY_TOKEN_SOURCE" \
  "$HOME/.config/training-assistant/garmin-tokenstore"
unset GARMIN_LEGACY_TOKEN_SOURCE
chmod -R go-rwx "$HOME/.config/training-assistant/garmin-tokenstore"
```

Set `GARMIN_TOKENSTORE_PATH` in `api/.env` to:

```text
~/.config/training-assistant/garmin-tokenstore
```

## Shadow and canary sequence

1. Run the contract and comparison tests.
2. Run the daily-summary worker with `--daily-only --days-back 2`.
3. Run the activity worker with `--activities-only --days-back 2`.
4. Verify row counts and Garmin IDs in PostgreSQL.
5. Run the calendar worker with `--calendar-only`.
6. Verify that races are present, assistant-owned generic calendar workouts are
   not imported, and the six current assistant plan entries remain linked.
7. Enable Peloton only after its credentials are present in `api/.env`, then run
   `scripts/garmin_sync.py --peloton --days-back 7`.
8. Exercise one approved workout writeback and verify both Garmin and
   `assistant_plan_entries`.

Record JSON reports outside git. Reports must not contain credentials or raw
activity exports.

## Scheduler cutover

Install the Training Assistant-owned job only after the canary sequence passes:

```bash
cp deploy/com.training.garmin-sync.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.training.garmin-sync.plist"
```

Before enabling it, unload the legacy Garmin jobs and verify that no old worker
process is running. The new worker uses
`/tmp/training-assistant-garmin-sync.lock`; only one writer may hold that lock.

Verify the scheduler:

```bash
launchctl print "gui/$(id -u)/com.training.garmin-sync"
cd api && ./scripts/run_garmin_sync.sh
```

## Rollback

If a canary, scheduled run, API health check, or data comparison fails:

```bash
launchctl bootout "gui/$(id -u)/com.training.garmin-sync" || true
# Re-enable the legacy scheduler using its preserved local LaunchAgent backup.
# Do not modify or restore the shared database.
```

Keep the old scheduler backup and token store until the soak period passes.
Rollback must not delete Garmin activity history, races, planned workouts, or
assistant plan entries.

## Recorded parity check (2026-07-14)

The Training Assistant-owned worker and the preserved legacy path were run over
the same two-day summary window and calendar window. Both reported three daily
summaries and six races with zero generic calendar workouts. The populated
PostgreSQL database remained at 255 Garmin activities, 31 daily summaries, five
races, six upcoming assistant workouts, and six successful assistant plan-entry
links. No duplicate upcoming plan rows were introduced.

## Soak completion

Retirement is allowed only after a complete operating window includes:

- One scheduled daily-summary and activity run.
- One scheduled calendar run.
- One successful on-demand API refresh.
- One assistant plan or approved workout writeback.
- One Peloton import when enabled.
- No duplicate Garmin IDs or stale assistant-owned calendar imports.
- Successful Tailnet plan, dashboard, activity, and race endpoint checks.
- A clean active-file scan showing no runtime dependency on the legacy
  repository.
