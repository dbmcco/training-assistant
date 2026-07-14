from pathlib import Path

from src.config import settings
from src.integrations.garmin.worker import GarminWorkerArgs
from src.services.garmin_refresh import _refresh_dashboard_data


def test_refresh_uses_configured_days_back(monkeypatch):
    captured: list[GarminWorkerArgs] = []

    def fake_run_worker(args: GarminWorkerArgs):
        captured.append(args)
        return {"status": "success", "domains": {"daily_summary": {"updated": 2}}}

    monkeypatch.setattr("src.services.garmin_refresh._run_worker", fake_run_worker)
    monkeypatch.setattr("src.services.garmin_refresh._acquire_lock", lambda: True)
    monkeypatch.setattr("src.services.garmin_refresh._release_lock", lambda: None)
    monkeypatch.setattr("src.services.garmin_refresh._load_last_success_epoch", lambda: None)
    monkeypatch.setattr("src.services.garmin_refresh._store_last_success_epoch", lambda _: None)
    monkeypatch.setattr(settings, "garmin_refresh_enabled", True)
    monkeypatch.setattr(settings, "garmin_refresh_min_interval_seconds", 0)
    monkeypatch.setattr(settings, "garmin_refresh_days_back", 2)

    result = _refresh_dashboard_data(force=True)

    assert result["status"] == "success"
    assert result["days_back"] == 2
    assert captured == [GarminWorkerArgs(daily_only=True, days_back=2)]


def test_refresh_clamps_negative_days_back(monkeypatch):
    captured: list[GarminWorkerArgs] = []

    def fake_run_worker(args: GarminWorkerArgs):
        captured.append(args)
        return {"status": "success"}

    monkeypatch.setattr("src.services.garmin_refresh._run_worker", fake_run_worker)
    monkeypatch.setattr("src.services.garmin_refresh._acquire_lock", lambda: True)
    monkeypatch.setattr("src.services.garmin_refresh._release_lock", lambda: None)
    monkeypatch.setattr("src.services.garmin_refresh._load_last_success_epoch", lambda: None)
    monkeypatch.setattr("src.services.garmin_refresh._store_last_success_epoch", lambda _: None)
    monkeypatch.setattr(settings, "garmin_refresh_enabled", True)
    monkeypatch.setattr(settings, "garmin_refresh_min_interval_seconds", 0)
    monkeypatch.setattr(settings, "garmin_refresh_days_back", -5)

    result = _refresh_dashboard_data(force=True)

    assert result["status"] == "success"
    assert result["days_back"] == 0
    assert captured == [GarminWorkerArgs(daily_only=True, days_back=0)]


def test_refresh_runs_calendar_in_assistant_mode_without_importing_generic_workouts(monkeypatch):
    captured: list[GarminWorkerArgs] = []

    def fake_run_worker(args: GarminWorkerArgs):
        captured.append(args)
        return {"status": "success", "domains": {"calendar": {"workouts": 0, "races": 1}}}

    monkeypatch.setattr("src.services.garmin_refresh._run_worker", fake_run_worker)
    monkeypatch.setattr("src.services.garmin_refresh._acquire_lock", lambda: True)
    monkeypatch.setattr("src.services.garmin_refresh._release_lock", lambda: None)
    monkeypatch.setattr("src.services.garmin_refresh._load_last_success_epoch", lambda: None)
    monkeypatch.setattr("src.services.garmin_refresh._store_last_success_epoch", lambda _: None)
    monkeypatch.setattr(settings, "garmin_refresh_enabled", True)
    monkeypatch.setattr(settings, "garmin_refresh_min_interval_seconds", 0)
    monkeypatch.setattr(settings, "garmin_refresh_days_back", 1)
    monkeypatch.setattr(settings, "plan_ownership_mode", "assistant")

    result = _refresh_dashboard_data(include_calendar=True, force=True)

    assert result["status"] == "success"
    assert result["include_calendar"] is True
    assert result["calendar_skipped_reason"] is None
    assert captured == [
        GarminWorkerArgs(daily_only=True, days_back=1),
        GarminWorkerArgs(calendar_only=True, days_back=1),
    ]
