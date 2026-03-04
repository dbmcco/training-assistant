from src.services.plan_changes import diff_plan_snapshots, summarize_plan_change


def test_diff_plan_snapshots_detects_added_removed_rescheduled_and_updated():
    workout_a = "00000000-0000-0000-0000-000000000001"
    workout_b = "00000000-0000-0000-0000-000000000002"
    workout_c = "00000000-0000-0000-0000-000000000003"
    workout_d = "00000000-0000-0000-0000-000000000004"

    before = {
        workout_a: {
            "id": workout_a,
            "date": "2026-03-04",
            "discipline": "run",
            "workout_type": "easy run",
            "target_duration": 45,
            "target_distance": None,
            "target_hr_zone": None,
            "description": "steady",
            "status": "upcoming",
        },
        workout_b: {
            "id": workout_b,
            "date": "2026-03-05",
            "discipline": "bike",
            "workout_type": "endurance ride",
            "target_duration": 90,
            "target_distance": None,
            "target_hr_zone": None,
            "description": "zone 2",
            "status": "upcoming",
        },
        workout_c: {
            "id": workout_c,
            "date": "2026-03-06",
            "discipline": "swim",
            "workout_type": "technique",
            "target_duration": 60,
            "target_distance": 2200.0,
            "target_hr_zone": None,
            "description": "drills",
            "status": "upcoming",
        },
    }
    after = {
        workout_a: {
            "id": workout_a,
            "date": "2026-03-05",
            "discipline": "run",
            "workout_type": "easy run",
            "target_duration": 45,
            "target_distance": None,
            "target_hr_zone": None,
            "description": "steady",
            "status": "upcoming",
        },
        workout_c: {
            "id": workout_c,
            "date": "2026-03-06",
            "discipline": "swim",
            "workout_type": "technique",
            "target_duration": 55,
            "target_distance": 2200.0,
            "target_hr_zone": None,
            "description": "drills",
            "status": "upcoming",
        },
        workout_d: {
            "id": workout_d,
            "date": "2026-03-07",
            "discipline": "bike",
            "workout_type": "recovery spin",
            "target_duration": 45,
            "target_distance": None,
            "target_hr_zone": None,
            "description": "easy",
            "status": "upcoming",
        },
    }

    events = diff_plan_snapshots(before, after)
    types = [event["event_type"] for event in events]
    assert "added" in types
    assert "removed" in types
    assert "rescheduled" in types
    assert "updated" in types


def test_summarize_plan_change_rescheduled():
    summary = summarize_plan_change(
        event_type="rescheduled",
        workout_date=None,
        previous_workout_date=None,
        discipline="run",
        workout_type="easy run",
        changed_fields=["date"],
    )
    assert "Moved run easy run" in summary
