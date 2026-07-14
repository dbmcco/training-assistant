# Garmin Synchronization Contract

This document freezes the observable contract that the Training Assistant-owned
Garmin worker must preserve while the sibling implementation is migrated.

## Sync report

Every worker invocation returns a JSON object with these top-level fields:

```json
{
  "status": "success",
  "domains": {
    "activities": {"status": "success", "created": 1, "updated": 2},
    "daily_summary": {"status": "success", "created": 1, "updated": 0},
    "calendar": {"status": "skipped", "reason": "assistant_owned_plan_mode"}
  },
  "counts": {"created": 2, "updated": 2, "deleted": 0},
  "created_ids": ["activity-123"],
  "updated_ids": ["activity-456"],
  "deleted_ids": [],
  "skipped": [],
  "failures": []
}
```

Required top-level fields are `status`, `domains`, `counts`, `created_ids`,
`updated_ids`, `deleted_ids`, `skipped`, and `failures`. A failed domain must
appear in `domains` and `failures`; a failed worker exits nonzero. Credentials,
token contents, and personal activity exports are never included.

The worker preserves these domain operations:

- Activities, including activity details, keyed by Garmin activity ID.
- Daily summaries keyed by calendar date.
- Biometrics keyed by athlete and date.
- Races and calendar items keyed by Garmin event or workout ID.
- Training plans and gear keyed by their Garmin identifiers.
- Peloton imports keyed by their source activity ID.

## Writeback result

Workout creation, replacement, and deletion return a JSON object compatible with
the existing application services:

```json
{
  "status": "success",
  "workout_id": "1632159732",
  "workout_date": "2026-07-20",
  "discipline": "run",
  "workout_type": "recovery_run",
  "deleted_existing_ids": [],
  "delete_failed_ids": []
}
```

Required fields are `status`, `workout_id` when successful, `workout_date`,
`discipline`, `deleted_existing_ids`, and `delete_failed_ids`. A failed or
unverified writeback must not claim success and must not replace the existing
assistant plan entry's Garmin ID.

## Ownership rules

When `PLAN_OWNERSHIP_MODE=assistant`:

- Training Assistant-generated workouts are authoritative.
- Generic Garmin calendar workout imports are skipped.
- Garmin activities, recovery metrics, races, and completed-workout evidence
  continue to be ingested.
- Assistant plan entries are updated only after a verified Garmin workout ID is
  returned.

## Operational contract

The worker supports daily-only, calendar-only, comprehensive, days-back, and
calendar-inclusion modes. It uses one process lock, releases the lock on every
failure path, and reports bounded stdout/stderr without secrets. The FastAPI
request path may trigger an on-demand worker operation through an adapter, but
long-running Garmin calls remain outside the request process.

The migration is complete only when the Training Assistant-owned worker
produces equivalent identifiers and domain outcomes, the public API responses
remain compatible, and no active runtime path references the sibling repository.
