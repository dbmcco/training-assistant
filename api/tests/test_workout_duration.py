from src.services.workout_duration import (
    format_planned_duration,
    normalize_planned_duration_minutes,
    planned_duration_seconds,
)


def test_normalize_planned_duration_minutes_handles_garmin_seconds():
    assert normalize_planned_duration_minutes(4020) == 67
    assert normalize_planned_duration_minutes(3300) == 55
    assert normalize_planned_duration_minutes(3780) == 63


def test_planned_duration_seconds_and_format_from_minutes():
    assert planned_duration_seconds(55) == 3300.0
    assert format_planned_duration(55) == "55m"
    assert format_planned_duration(4020) == "1h 7m"
