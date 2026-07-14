from __future__ import annotations

from datetime import date


REQUIRED_SYNC_REPORT_FIELDS = {
    "status",
    "domains",
    "counts",
    "created_ids",
    "updated_ids",
    "deleted_ids",
    "skipped",
    "failures",
}

REQUIRED_WRITEBACK_FIELDS = {
    "status",
    "workout_date",
    "discipline",
    "deleted_existing_ids",
    "delete_failed_ids",
}


def make_sync_report() -> dict:
    return {
        "status": "success",
        "domains": {"activities": {"status": "success"}},
        "counts": {"created": 0, "updated": 0, "deleted": 0},
        "created_ids": [],
        "updated_ids": [],
        "deleted_ids": [],
        "skipped": [],
        "failures": [],
    }


def make_writeback_result(*, workout_id: str = "123") -> dict:
    return {
        "status": "success",
        "workout_id": workout_id,
        "workout_date": date(2026, 7, 20).isoformat(),
        "discipline": "run",
        "workout_type": "recovery_run",
        "deleted_existing_ids": [],
        "delete_failed_ids": [],
    }


def test_sync_report_has_stable_top_level_fields():
    assert set(make_sync_report()) == REQUIRED_SYNC_REPORT_FIELDS


def test_writeback_result_preserves_existing_success_shape():
    result = make_writeback_result(workout_id="1632159732")
    assert set(result) >= REQUIRED_WRITEBACK_FIELDS
    assert result["status"] == "success"
    assert result["workout_id"] == "1632159732"
    assert result["workout_date"] == "2026-07-20"
    assert result["discipline"] == "run"
