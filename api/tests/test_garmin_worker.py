from __future__ import annotations

from datetime import date

from src.config import Settings
from src.integrations.garmin.config import GarminIntegrationSettings
from src.integrations.garmin.worker import GarminWorker, GarminWorkerArgs


class FakeClient:
    def __init__(self, integration_settings):
        self.integration_settings = integration_settings
        self.closed = False

    def ensure_schema(self):
        return None

    def sync_activities(self, days_back):
        assert days_back == 2
        return 3

    def sync_daily_range(self, start, end):
        assert end == date.today()
        assert (end - start).days == 2
        return 2

    def sync_calendar(self, months_ahead):
        assert months_ahead == 5
        return {"races": 1, "workouts": 2}

    def full_sync(self, days_back, *, comprehensive, include_calendar):
        return {"activities_synced": 3, "days_synced": 2}

    def close(self):
        self.closed = True


def integration_settings(tmp_path):
    return GarminIntegrationSettings.from_app_settings(
        Settings(
            garmin_sync_lock_path=str(tmp_path / "garmin-sync.lock"),
            garmin_tokenstore_path=str(tmp_path / "tokens"),
            garmin_calendar_months_ahead=5,
        )
    )


def test_worker_runs_daily_sync_and_releases_lock(tmp_path):
    settings = integration_settings(tmp_path)
    worker = GarminWorker(settings, client_factory=FakeClient)

    report = worker.run(GarminWorkerArgs(daily_only=True, days_back=2))

    assert report["status"] == "success"
    assert report["domains"]["daily_summary"]["updated"] == 2
    assert not settings.lock_path.exists()


def test_worker_peloton_flag_does_not_run_full_garmin_sync_when_disabled(tmp_path):
    settings = integration_settings(tmp_path)
    worker = GarminWorker(settings, client_factory=FakeClient)

    report = worker.run(GarminWorkerArgs(peloton=True, days_back=7))

    assert report["status"] == "success"
    assert report["domains"]["peloton"]["status"] == "skipped"
    assert report["domains"]["peloton"]["reason"] == "peloton_disabled"


def test_worker_skips_when_disabled(tmp_path):
    app_settings = Settings(
        garmin_integration_enabled=False,
        garmin_sync_lock_path=str(tmp_path / "garmin-sync.lock"),
    )
    settings = GarminIntegrationSettings.from_app_settings(app_settings)

    report = GarminWorker(settings, client_factory=FakeClient).run(GarminWorkerArgs())

    assert report["status"] == "skipped"
    assert report["skipped"][0]["reason"] == "garmin_integration_disabled"


def test_worker_skips_when_another_process_holds_lock(tmp_path):
    settings = integration_settings(tmp_path)
    settings.lock_path.mkdir()

    report = GarminWorker(settings, client_factory=FakeClient).run(GarminWorkerArgs())

    assert report["status"] == "skipped"
    assert report["skipped"][0]["reason"] == "sync_already_running"
    settings.lock_path.rmdir()
