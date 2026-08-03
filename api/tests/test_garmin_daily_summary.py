from src.integrations.garmin.sync_engine import intensity_minutes_from_summary


def test_intensity_minutes_sourced_from_user_summary():
    summary = {"moderateIntensityMinutes": 21, "vigorousIntensityMinutes": 24}
    assert intensity_minutes_from_summary(summary) == (21, 24)


def test_intensity_minutes_handles_string_values():
    # Garmin payloads sometimes carry these as JSON strings.
    assert intensity_minutes_from_summary(
        {"moderateIntensityMinutes": "37", "vigorousIntensityMinutes": "2"}
    ) == (37, 2)


def test_intensity_minutes_zero_is_preserved():
    # Rest days legitimately report 0; must not be coerced to None, otherwise the
    # upsert's COALESCE would keep a stale prior value instead of the real 0.
    assert intensity_minutes_from_summary(
        {"moderateIntensityMinutes": 0, "vigorousIntensityMinutes": 0}
    ) == (0, 0)


def test_intensity_minutes_missing_or_non_dict_returns_none():
    assert intensity_minutes_from_summary({}) == (None, None)
    assert intensity_minutes_from_summary(None) == (None, None)
    assert intensity_minutes_from_summary("not-a-dict") == (None, None)
