from pathlib import Path

from src.config import Settings
from src.integrations.garmin.config import GarminIntegrationSettings


def test_garmin_settings_default_to_training_assistant_paths(tmp_path):
    app_settings = Settings(
        garmin_tokenstore_path=str(tmp_path / "garmin-tokenstore"),
        garmin_sync_lock_path=str(tmp_path / "garmin-sync.lock"),
    )

    integration = GarminIntegrationSettings.from_app_settings(app_settings)

    assert integration.tokenstore_path == tmp_path / "garmin-tokenstore"
    assert integration.lock_path == tmp_path / "garmin-sync.lock"
    assert integration.tokenstore_path.name == "garmin-tokenstore"


def test_assistant_plan_mode_is_preserved():
    app_settings = Settings(plan_ownership_mode="assistant")

    assert GarminIntegrationSettings.from_app_settings(app_settings).plan_ownership_mode == "assistant"


def test_negative_windows_are_clamped_and_timeout_has_safe_floor():
    app_settings = Settings(
        garmin_sync_days_back=-5,
        garmin_calendar_months_ahead=-2,
        garmin_sync_timeout_seconds=0,
    )

    integration = GarminIntegrationSettings.from_app_settings(app_settings)

    assert integration.days_back == 0
    assert integration.calendar_months_ahead == 0
    assert integration.timeout_seconds == 5
