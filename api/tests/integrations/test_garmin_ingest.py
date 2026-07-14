from datetime import date

from src.integrations.garmin.sync_engine import GarminSyncClient, _calendar_workout_record


def test_calendar_workout_record_preserves_assistant_workout_identity():
    record = _calendar_workout_record(
        {
            "itemType": "workout",
            "workoutId": 1632159732,
            "date": "2026-07-20",
            "title": "Run recovery_run (2026-07-20)",
            "sportTypeKey": "running",
        },
        today=date(2026, 7, 14),
    )

    assert record == {
        "workout_uuid": "calendar-workout-1632159732-2026-07-20",
        "workout_id": "1632159732",
        "date": date(2026, 7, 20),
        "discipline": "running",
        "workout_type": "recovery_run",
        "title": "Run recovery_run (2026-07-20)",
        "status": "upcoming",
        "training_plan_id": "0",
    }


def test_calendar_workout_record_rejects_non_workout_items():
    assert _calendar_workout_record({"itemType": "race", "date": "2026-07-20"}) is None


def test_client_accepts_training_assistant_integration_settings(tmp_path):
    from src.config import Settings
    from src.integrations.garmin.config import GarminIntegrationSettings

    integration = GarminIntegrationSettings.from_app_settings(
        Settings(
            garmin_tokenstore_path=str(tmp_path / "tokens"),
            garmin_sync_lock_path=str(tmp_path / "lock"),
        )
    )
    client = GarminSyncClient(integration)

    assert client._integration_settings.tokenstore_path == tmp_path / "tokens"
    client.close()
