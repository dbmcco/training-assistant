# Garmin Integration Retirement Design

**Date:** 2026-07-14  
**Status:** Approved for implementation  
**Owner:** Training Assistant

## Goal

Make `training-assistant` operationally independent of the sibling
`garmin-connect-sync` repository without changing the user-facing Training
Assistant behavior, losing Garmin data, or allowing two sync systems to write
competing records during the migration.

The end state is that the Training Assistant repository contains the Garmin and
Peloton integration code, owns the Garmin database tables and scheduled jobs,
and has no runtime, configuration, documentation, or test dependency on the
old sibling repository.

## Current Boundary

Training Assistant already owns the application-facing behavior:

- Dashboard, readiness, activities, races, plan, adherence, and coach APIs.
- Assistant-owned plan generation and plan-entry sync status.
- The public refresh endpoint and recommendation approval pipeline.
- The database models for Garmin-backed records and assistant plan records.

The sibling repository currently owns the implementation and operations behind
that boundary:

- Garmin authentication and API access.
- Activity, daily summary, biometric, activity-detail, gear, training-plan,
race, and calendar ingestion.
- Peloton-to-Garmin import.
- Garmin workout creation, replacement, deletion, and deduplication.
- Scheduled shell scripts and macOS LaunchAgents.

Training Assistant currently reaches into the sibling repository through
`api/src/services/garmin_refresh.py` and
`api/src/services/garmin_writeback.py`.

## Chosen Architecture

Move the integration into `training-assistant` as a separate worker package,
not into the FastAPI request process.

The target structure is:

```text
training-assistant/
  api/src/integrations/garmin/
    client.py              # authentication and Garmin API boundary
    ingest.py              # activities, summaries, biometrics, details, gear
    calendar.py            # races, calendar items, ownership filtering
    workouts.py            # create, replace, delete, deduplicate
    peloton.py             # Peloton-to-Garmin bridge
    locks.py               # single-writer coordination
  api/src/services/garmin_refresh.py
  api/src/services/garmin_writeback.py
  api/scripts/garmin_sync.py
  deploy/com.training.garmin-sync.plist
```

The exact module split may follow the existing code if preserving behavior
requires fewer seams, but the worker must remain independently executable and
must not run long Garmin calls inside FastAPI request handlers.

The API-facing services will stop resolving a filesystem path to
`garmin-connect-sync`. They will call the internal integration boundary or
invoke the Training Assistant-owned worker command with a stable JSON contract.
The public API routes, coach tools, plan ownership mode, and assistant plan
entry status vocabulary remain unchanged.

## Data Ownership and Invariants

1. Training Assistant is the only application that writes the canonical
   Garmin-backed tables after cutover.
2. Assistant-owned plans remain authoritative. In
   `PLAN_OWNERSHIP_MODE=assistant`, generic Garmin calendar workout imports are
   ignored so old Garmin workouts cannot reappear in the assistant plan.
3. Existing Garmin IDs, activity history, completed-workout links, race rows,
   plan rows, and assistant plan-entry rows are preserved.
4. Every write operation is idempotent by the existing Garmin identifier or by
   the existing date-and-discipline replacement rule.
5. Only one scheduled writer may run at a time. The old and new schedulers must
   never be enabled together.
6. A failed Garmin call records a failed or retryable status and never reports a
   workout as successfully synced without a verified Garmin ID.
7. The old repository remains available as a rollback source until the new
   worker completes the soak period.

## Database Migration

The existing tables `garmin_activities`, `garmin_daily_summary`, and
`athlete_biometrics` are currently treated as externally created by Alembic.
The migration will:

1. Capture the live schema, indexes, constraints, row counts, and nullability
   before changing ownership.
2. Add explicit Training Assistant migration ownership for those tables without
   dropping or recreating populated tables destructively.
3. Add only missing indexes or constraints after comparing the live schema.
4. Preserve existing foreign-key relationships from planned workouts and
   activities.
5. Add a migration verification command that compares pre- and post-migration
   counts and identifier sets.

The migration must be safe to run against the current populated database and
safe to run again in a clean test database.

## Staged Cutover

### Stage 1: Inventory and contracts

Freeze the current behavior in tests and capture the operational contract:
configuration, token-store location, command arguments, JSON payloads, table
schemas, scheduler cadence, and expected sync result summaries.

### Stage 2: Internal implementation

Copy the working Garmin integration into the Training Assistant repository with
minimal behavior changes. Add dependencies and configuration to Training
Assistant. Keep the old implementation untouched during this stage.

### Stage 3: Shadow validation

Run the Training Assistant-owned worker in dry-run or comparison mode. It may
read Garmin and calculate writes, but it must not create competing database
rows or Garmin workouts. Compare activity IDs, dates, race records, calendar
ownership decisions, and planned-workout actions against the known-good path.

### Stage 4: Canary writes

Enable Training Assistant-owned writes for one domain at a time:

1. Daily summaries and biometrics.
2. Activities and activity details.
3. Races and calendar ingestion.
4. Assistant plan workout writeback.
5. Peloton-to-Garmin import.

Each canary requires focused tests, a live smoke check, and a rollback point.

### Stage 5: Scheduler cutover

Install the Training Assistant-owned LaunchAgents and disable the sibling
LaunchAgents. Keep the command cadence and lock behavior equivalent at first.
The existing on-demand refresh endpoint must use the new worker before the old
scheduler is disabled.

### Stage 6: Soak and retirement

Observe at least one complete operational window covering scheduled ingestion,
manual refresh, a plan writeback, calendar ownership, and Peloton import.
Verify no duplicate rows, stale plan re-imports, missing activities, or failed
status transitions. Then archive the sibling repository, remove its runtime
configuration and documentation references, and leave a rollback tag or
archive outside the active runtime path.

## Failure Handling and Rollback

The new worker must expose structured results containing the operation, counts,
created/updated/deleted identifiers, skipped items, and failures. Logs must
identify the domain and date range without leaking credentials.

Rollback is deliberately simple:

1. Stop and disable Training Assistant-owned Garmin jobs.
2. Re-enable the old scheduler.
3. Set the refresh/writeback provider back to the legacy adapter if needed.
4. Leave the shared database unchanged; do not restore a database backup merely
   to roll back a code deployment.

Retirement is prohibited until this rollback path has been exercised in a
non-destructive validation run.

## Verification Gates

The migration is complete only when all of the following are true:

- The full Training Assistant API test suite passes.
- The Garmin worker test suite has been moved into Training Assistant and passes.
- Clean-database migrations create all required Garmin-backed tables.
- A populated-database migration preserves row counts and identifiers.
- On-demand refresh succeeds without importing the old repository.
- Scheduled sync succeeds from a Training Assistant-owned LaunchAgent.
- Assistant plan generation and approved workout changes sync successfully and
  update `assistant_plan_entries` atomically.
- Assistant-owned mode does not re-import generic Garmin calendar workouts.
- Peloton import still creates the expected Garmin activity records.
- The Tailnet dashboard, plan, activity, race, and refresh endpoints return
  their existing successful responses.
- `rg` finds no active runtime or documentation reference to the sibling
  `garmin-connect-sync` repository.
- The old LaunchAgents are disabled and no old sync process is running.

## Explicitly Out of Scope

- Rewriting the Garmin API client for stylistic reasons.
- Changing the Training Assistant public API or frontend behavior.
- Changing the assistant plan algorithm or race prioritization logic.
- Moving historical Garmin data to a new database.
- Adding new training features during the integration.
- Deleting the old repository before the soak and rollback gates pass.

## Residual Risks to Track

- Garmin authentication and token refresh behavior may differ when the token
  store moves under Training Assistant configuration.
- The existing synchronous Garmin client may need process isolation to avoid
  blocking the API worker.
- The live database schema may contain indexes or columns not represented in
  the repository's current model definitions.
- Garmin calendar responses may contain duplicate or stale items across month
  boundaries; comparison tests must use Garmin IDs and dates, not titles alone.
- The existing writeback subprocess has experienced timeouts; the internal
  worker must preserve timeout, retry, deduplication, and atomic status updates.
