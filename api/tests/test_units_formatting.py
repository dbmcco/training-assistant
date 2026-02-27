from src.services.units import (
    format_distance_from_kilometers,
    format_distance_from_meters,
    format_pace_per_mile,
)


def test_format_distance_from_meters_run_uses_miles():
    assert format_distance_from_meters(1609.344, "run") == "1.0 mi"


def test_format_distance_from_meters_swim_uses_yards():
    assert format_distance_from_meters(1000, "swim") == "1,094 yd"


def test_format_distance_from_kilometers_swim_uses_yards():
    assert format_distance_from_kilometers(1.8, "swim") == "1,969 yd"


def test_format_pace_per_mile():
    assert format_pace_per_mile(300) == "8:03/mi"
