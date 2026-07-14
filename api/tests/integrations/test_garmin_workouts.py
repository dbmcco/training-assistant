from src.integrations.garmin.workouts import GarminWorkoutWriter


class FakeSync:
    client = object()

    def close(self):
        pass


def test_writer_replaces_matching_workout_and_returns_new_id(monkeypatch):
    calls = []

    class FakeGarminWriter:
        def __init__(self, _client):
            pass

        def find_matching_workout_ids(self, **kwargs):
            calls.append(("find", kwargs))
            return ["old-123"]

        def delete_workout(self, workout_id):
            calls.append(("delete", workout_id))
            return True

        def create_and_schedule(self, **kwargs):
            calls.append(("create", kwargs))
            return "new-456"

        def list_scheduled_workouts_for_date(self, _date):
            return []

    monkeypatch.setattr("src.integrations.garmin.workouts.GarminWriter", FakeGarminWriter)
    writer = GarminWorkoutWriter(FakeSync())

    result = writer.apply_change(
        {
            "workout_date": "2026-07-20",
            "discipline": "run",
            "workout_type": "recovery_run",
            "description": "Easy recovery",
            "workout_steps": [],
        }
    )

    assert result["status"] == "success"
    assert result["workout_id"] == "new-456"
    assert result["deleted_existing_ids"] == ["old-123"]
    assert calls[1] == ("delete", "old-123")
