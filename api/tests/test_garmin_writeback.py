from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from src.config import settings
from src.services.garmin_writeback import (
    _discipline_matches,
    _run_writeback,
    _run_writeback_with_verify,
    _workout_matches,
    verify_writeback,
)


def test_discipline_matches_known_mappings():
    assert _discipline_matches("running", "running") is True
    assert _discipline_matches("cycling", "cycling") is True
    assert _discipline_matches("swimming", "swimming") is True
    assert _discipline_matches("strength_training", "strength") is True
    assert _discipline_matches("yoga", "flexibility") is True


def test_discipline_matches_case_insensitive():
    assert _discipline_matches("Running", "RUNNING") is True
    assert _discipline_matches("CYCLING", "cycling") is True


def test_discipline_matches_unknown_returns_false():
    assert _discipline_matches("rowing", "running") is False
    assert _discipline_matches("", "running") is False


def test_workout_matches_by_discipline():
    item = {"sport_type_key": "running", "title": "Some Workout", "date": "2026-04-13"}
    assert _workout_matches(item, "running", "easy", "2026-04-13") is True


def test_workout_matches_by_title_fallback():
    item = {
        "sport_type_key": "",
        "title": "Running Easy (2026-04-13)",
        "date": "2026-04-13",
    }
    assert _workout_matches(item, "running", "Easy", "2026-04-13") is True


def test_workout_matches_no_match():
    item = {"sport_type_key": "cycling", "title": "Cycling Tempo", "date": "2026-04-13"}
    assert _workout_matches(item, "running", "easy", "2026-04-13") is False


def test_run_writeback_uses_internal_writer(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_enabled", True)
    calls = []

    class FakeWriter:
        def __init__(self, sync_client):
            calls.append(sync_client)

        def apply_change(self, payload):
            return {"status": "success", "workout_id": "789", "workout_date": payload["workout_date"]}

        def close(self):
            calls.append("closed")

    class FakeSync:
        def __init__(self, _settings):
            pass

        def close(self):
            calls.append("sync-closed")

    monkeypatch.setattr("src.services.garmin_writeback.GarminSyncClient", FakeSync)
    monkeypatch.setattr("src.services.garmin_writeback.GarminWorkoutWriter", FakeWriter)

    result = _run_writeback({"workout_date": "2026-04-13", "discipline": "run"})

    assert result["status"] == "success"
    assert result["workout_id"] == "789"
    assert calls[-1] == "closed"


def test_verify_writeback_timeout(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)

    class FakeWriter:
        def __init__(self, _sync):
            pass

        def scheduled_workouts(self, _date):
            raise TimeoutError

        def close(self):
            pass

    monkeypatch.setattr("src.services.garmin_writeback.GarminSyncClient", lambda _settings: object())
    monkeypatch.setattr("src.services.garmin_writeback.GarminWorkoutWriter", FakeWriter)

    result = verify_writeback(
        workout_date="2026-04-13", discipline="running", workout_type="easy", timeout_seconds=1
    )

    assert result["verified"] is False
    assert result["error"] == "verification_timeout"


def test_verify_writeback_found_matching_workout(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)

    class FakeWriter:
        def __init__(self, _sync):
            pass

        def scheduled_workouts(self, target_date):
            assert target_date == date(2026, 4, 13)
            return [
                {"workout_id": "456", "title": "Running Easy (2026-04-13)", "sport_type_key": "running", "date": "2026-04-13"}
            ]

        def close(self):
            pass

    monkeypatch.setattr("src.services.garmin_writeback.GarminSyncClient", lambda _settings: object())
    monkeypatch.setattr("src.services.garmin_writeback.GarminWorkoutWriter", FakeWriter)

    result = verify_writeback(
        workout_date="2026-04-13", discipline="running", workout_type="easy"
    )

    assert result["verified"] is True
    assert result["match_details"]["workout_id"] == "456"


def test_run_writeback_with_verify_failed_writeback(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)
    with patch(
        "src.services.garmin_writeback._run_writeback",
        return_value={"status": "failed", "reason": "auth"},
    ):
        result = _run_writeback_with_verify({"workout_date": "2026-04-13", "discipline": "running"})
    assert result["verification_status"] == "failed"


def test_run_writeback_with_verify_skipped(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)
    with patch(
        "src.services.garmin_writeback._run_writeback",
        return_value={"status": "skipped", "reason": "garmin_writeback_disabled"},
    ):
        result = _run_writeback_with_verify({"workout_date": "2026-04-13", "discipline": "running"})
    assert result["verification_status"] == "skipped"


def test_run_writeback_with_verify_success(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)
    with (
        patch("src.services.garmin_writeback._run_writeback", return_value={"status": "success", "workout_id": "789"}),
        patch("src.services.garmin_writeback.verify_writeback", return_value={"verified": True, "match_details": {"workout_id": "789"}, "error": None}),
    ):
        result = _run_writeback_with_verify({"workout_date": "2026-04-13", "discipline": "running", "workout_type": "easy"})
    assert result["verification_status"] == "success"
    assert result["verification_details"]["workout_id"] == "789"


def test_run_writeback_with_verify_unverified(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)
    with (
        patch("src.services.garmin_writeback._run_writeback", return_value={"status": "success", "workout_id": "789"}),
        patch("src.services.garmin_writeback.verify_writeback", return_value={"verified": False, "match_details": None, "error": "no_matching_workout_found"}),
    ):
        result = _run_writeback_with_verify({"workout_date": "2026-04-13", "discipline": "running", "workout_type": "easy"})
    assert result["verification_status"] == "synced_unverified"
    assert result["verification_error"] == "no_matching_workout_found"


def test_run_writeback_with_verify_disabled(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", False)
    with patch("src.services.garmin_writeback._run_writeback", return_value={"status": "success", "workout_id": "789"}):
        result = _run_writeback_with_verify({"workout_date": "2026-04-13", "discipline": "running"})
    assert result["verification_status"] == "success"


def test_run_writeback_with_verify_missing_date_discipline(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)
    with patch("src.services.garmin_writeback._run_writeback", return_value={"status": "success", "workout_id": "789"}):
        result = _run_writeback_with_verify({})
    assert result["verification_status"] == "synced_unverified"
    assert result["verification_error"] == "missing_workout_date_or_discipline_for_verify"
