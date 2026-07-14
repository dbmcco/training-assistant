from src.scripts.compare_garmin_sync import compare_reports


def test_comparison_ignores_order_but_detects_no_difference():
    expected = {
        "status": "success",
        "domains": {"activities": {"updated": 2}},
        "counts": {"updated": 2},
        "created_ids": ["a", "b"],
        "updated_ids": [],
        "deleted_ids": [],
        "skipped": [],
        "failures": [],
    }
    actual = {**expected, "created_ids": ["b", "a"]}

    report = compare_reports(expected, actual)

    assert report["status"] == "match"
    assert report["differences"] == []


def test_comparison_flags_duplicate_workout_ids():
    expected = {"status": "success", "created_ids": [], "updated_ids": []}
    actual = {"status": "success", "created_ids": ["workout-123", "workout-123"], "updated_ids": []}

    report = compare_reports(expected, actual)

    assert report["status"] == "different"
    assert report["duplicate_candidates"] == ["workout-123"]
