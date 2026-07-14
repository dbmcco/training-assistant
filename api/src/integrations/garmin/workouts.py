from __future__ import annotations

from datetime import date
from typing import Any

from src.integrations.garmin.sync_engine import GarminSyncClient
from src.integrations.garmin.writer import GarminWriter


class GarminWorkoutWriter:
    """Create, replace, delete, and verify Garmin calendar workouts internally."""

    def __init__(self, sync_client: GarminSyncClient | None = None) -> None:
        self.sync_client = sync_client or GarminSyncClient()
        self.writer = GarminWriter(self.sync_client.client)

    def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        workout_date = date.fromisoformat(str(payload["workout_date"]))
        discipline = str(payload.get("discipline") or "other").strip().lower()
        workout_type = str(payload.get("workout_type") or "adjusted").strip()
        name = f"{discipline.title()} {workout_type} ({workout_date.isoformat()})"
        steps = payload.get("workout_steps") or []
        replace_id = str(payload.get("replace_workout_id") or "").strip()
        candidate_ids = [replace_id] if replace_id else []
        if not candidate_ids and payload.get("dedupe_by_title", True):
            candidate_ids = self.writer.find_matching_workout_ids(
                target_date=workout_date,
                workout_name=name,
                sport_type=discipline,
            )

        deleted_existing_ids: list[str] = []
        delete_failed_ids: list[str] = []
        for workout_id in candidate_ids:
            if self.writer.delete_workout(workout_id):
                deleted_existing_ids.append(workout_id)
            else:
                delete_failed_ids.append(workout_id)

        if delete_failed_ids:
            return {
                "status": "failed",
                "reason": "failed_to_delete_existing_workout",
                "workout_date": workout_date.isoformat(),
                "discipline": discipline,
                "deleted_existing_ids": deleted_existing_ids,
                "delete_failed_ids": delete_failed_ids,
            }

        workout_id = self.writer.create_and_schedule(
            name=name,
            sport_type=discipline,
            steps=steps,
            target_date=workout_date,
            description=str(payload.get("description") or payload.get("recommendation_text") or ""),
        )
        if not workout_id:
            return {
                "status": "failed",
                "reason": "garmin_workout_create_or_schedule_failed",
                "workout_date": workout_date.isoformat(),
                "discipline": discipline,
                "deleted_existing_ids": deleted_existing_ids,
                "delete_failed_ids": delete_failed_ids,
            }

        return {
            "status": "success",
            "workout_id": str(workout_id),
            "workout_date": workout_date.isoformat(),
            "discipline": discipline,
            "workout_type": workout_type,
            "deleted_existing_ids": deleted_existing_ids,
            "delete_failed_ids": delete_failed_ids,
        }

    def delete(self, workout_id: str) -> dict[str, Any]:
        ok = self.writer.delete_workout(str(workout_id))
        return {
            "status": "success" if ok else "failed",
            "action": "delete",
            "workout_id": str(workout_id),
        }

    def scheduled_workouts(self, workout_date: date) -> list[dict[str, Any]]:
        return self.writer.list_scheduled_workouts_for_date(workout_date)

    def close(self) -> None:
        self.sync_client.close()
