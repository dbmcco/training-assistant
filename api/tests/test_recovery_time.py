from src.services.recovery_time import normalize_recovery_time_hours


def test_normalize_recovery_time_from_training_readiness_payload():
    raw_data = {
        "training_readiness": [
            {"score": 61, "recoveryTime": 1048},
        ]
    }
    assert normalize_recovery_time_hours(1048, raw_data) == 17.5


def test_normalize_recovery_time_from_morning_readiness_payload():
    raw_data = {"morning_readiness": {"score": 75, "recoveryTime": 55}}
    assert normalize_recovery_time_hours(55, raw_data) == 0.9


def test_normalize_recovery_time_large_value_without_raw_data():
    assert normalize_recovery_time_hours(1200, None) == 20.0


def test_normalize_recovery_time_small_value_without_raw_data_kept_as_hours():
    assert normalize_recovery_time_hours(24, None) == 24.0
