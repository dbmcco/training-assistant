"""One-shot live Garmin writeback canary.

Exercises the real production writeback path end to end on a far-future,
empty date so it cannot collide with real training:
  1. apply_change (create + schedule) via _run_writeback
  2. verify_writeback (read back from Garmin calendar)
  3. delete the created workout (cleanup)
  4. re-verify it is gone

Leaves the athlete's Garmin calendar exactly as it was.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.garmin_writeback import (
    _run_writeback,
    fallback_writeback_payload,
    verify_writeback,
)
from src.integrations.garmin.config import GarminIntegrationSettings
from src.integrations.garmin.sync_engine import GarminSyncClient
from src.integrations.garmin.workouts import GarminWorkoutWriter

CANARY_DATE = "2027-03-15"
CANARY_DISCIPLINE = "other"
CANARY_TYPE = "TA Writeback Canary"


def main() -> int:
    report: dict[str, object] = {"canary_date": CANARY_DATE}

    # 1. Create + schedule through the production path.
    payload = fallback_writeback_payload(
        workout_date=CANARY_DATE,
        discipline=CANARY_DISCIPLINE,
        workout_type=CANARY_TYPE,
        target_duration=10,
        description="Training Assistant writeback canary — automated test, safe to delete.",
        workout_steps=[{"type": "interval", "duration_minutes": 10, "notes": "canary"}],
        dedupe_by_title=True,
    )
    write_result = _run_writeback(payload)
    report["write"] = write_result
    print("WRITE:", json.dumps(write_result, default=str))

    if write_result.get("status") != "success":
        print("CANARY: write step did not succeed; aborting before verify.", file=sys.stderr)
        print("FULL REPORT:", json.dumps(report, default=str))
        return 1

    workout_id = str(write_result["workout_id"])

    # 2. Verify it landed on the Garmin calendar.
    verify_result = verify_writeback(
        workout_date=CANARY_DATE,
        discipline=CANARY_DISCIPLINE,
        workout_type=CANARY_TYPE,
    )
    report["verify_after_write"] = verify_result
    print("VERIFY:", json.dumps(verify_result, default=str))

    # 3. Cleanup — delete the canary workout we just created.
    cleanup: dict[str, object] = {}
    try:
        settings = GarminIntegrationSettings.from_app_settings()
        client = GarminSyncClient(settings)
        writer = GarminWorkoutWriter(client)
        cleanup = writer.delete(workout_id)
        writer.close()
    except Exception as exc:  # noqa: BLE001 - report, do not hide
        cleanup = {"status": "failed", "error": f"cleanup_exception: {exc}"}
    report["cleanup"] = cleanup
    print("CLEANUP:", json.dumps(cleanup, default=str))

    # 4. Re-verify the canary is gone.
    reverify = verify_writeback(
        workout_date=CANARY_DATE,
        discipline=CANARY_DISCIPLINE,
        workout_type=CANARY_TYPE,
    )
    report["verify_after_cleanup"] = reverify
    print("REVERIFY:", json.dumps(reverify, default=str))

    # Outcome: write succeeded, verify-after-write saw it, cleanup deleted it.
    created_ok = bool(write_result.get("status") == "success")
    landed_ok = bool(report["verify_after_write"].get("verified"))
    deleted_ok = cleanup.get("status") == "success"

    report["canary_pass"] = bool(created_ok and landed_ok and deleted_ok)
    print("CANARY_PASS:", report["canary_pass"])
    if not report["canary_pass"]:
        print("CANARY: incomplete — see report. Workout may still exist on Garmin; "
              f"manual delete id={workout_id} on {CANARY_DATE} if cleanup failed.",
              file=sys.stderr)

    print("FULL REPORT:", json.dumps(report, default=str))
    return 0 if report["canary_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
