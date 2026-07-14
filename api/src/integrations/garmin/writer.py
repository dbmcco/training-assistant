# ABOUTME: Garmin Connect write operations — create, schedule, update, cancel workouts.
# ABOUTME: Uses garth connectapi directly since garminconnect library lacks write methods.

import json
from datetime import date
from typing import Any, Dict, List, Optional


SPORT_TYPE_MAP = {
    "run": {"sportTypeId": 1, "sportTypeKey": "running"},
    "running": {"sportTypeId": 1, "sportTypeKey": "running"},
    "bike": {"sportTypeId": 2, "sportTypeKey": "cycling"},
    "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling"},
    "swim": {"sportTypeId": 4, "sportTypeKey": "lap_swimming"},
    "swimming": {"sportTypeId": 4, "sportTypeKey": "lap_swimming"},
    "strength": {"sportTypeId": 13, "sportTypeKey": "strength_training"},
    "other": {"sportTypeId": 99, "sportTypeKey": "other"},
}


def build_workout_payload(
    name: str,
    sport_type: str,
    steps: List[Dict[str, Any]],
    description: str = "",
) -> Dict[str, Any]:
    normalized_sport = str(sport_type or "other").strip().lower()
    sport = SPORT_TYPE_MAP.get(normalized_sport, SPORT_TYPE_MAP["other"])

    workout_steps = []
    for i, step in enumerate(steps):
        ws = {
            "type": "ExecutableStepDTO",
            "stepOrder": i + 1,
            "stepType": {
                "stepTypeId": _step_type_id(step.get("type", "interval")),
                "stepTypeKey": step.get("type", "interval"),
            },
            "endCondition": {
                "conditionTypeId": 2,
                "conditionTypeKey": "time",
            },
            "endConditionValue": step.get("duration_minutes", 10) * 60,
        }
        if step.get("notes"):
            ws["description"] = step["notes"]
        workout_steps.append(ws)

    return {
        "workoutName": name,
        "description": description,
        "sportType": sport,
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": sport,
            "workoutSteps": workout_steps,
        }],
    }


def _step_type_id(step_type: str) -> int:
    return {
        "warmup": 1, "cooldown": 2, "interval": 3,
        "recovery": 4, "rest": 5, "repeat": 6,
    }.get(step_type, 3)


class GarminWriter:
    def __init__(self, garmin_client) -> None:
        self.client = garmin_client
        self.garth = garmin_client.garth

    def create_workout(
        self,
        name: str,
        sport_type: str,
        steps: List[Dict[str, Any]],
        description: str = "",
    ) -> Optional[Dict[str, Any]]:
        payload = build_workout_payload(name, sport_type, steps, description)
        resp = self.garth.post("connectapi", "/workout-service/workout", json=payload)
        if hasattr(resp, "status_code") and resp.status_code >= 400:
            return None
        return resp.json() if hasattr(resp, "json") else resp

    def list_scheduled_workouts_for_date(self, target_date: date) -> List[Dict[str, Any]]:
        month_endpoint = (
            f"/calendar-service/year/{target_date.year}/month/{target_date.month - 1}"
        )
        try:
            resp = self.garth.connectapi(month_endpoint)
        except Exception:
            return []

        if not isinstance(resp, dict):
            return []
        raw_items = resp.get("calendarItems")
        if not isinstance(raw_items, list):
            return []

        wanted_date = target_date.isoformat()
        workouts: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_date = str(item.get("date") or item.get("calendarDate") or "")
            if item_date != wanted_date:
                continue

            workout_id = item.get("workoutId")
            if workout_id is None:
                adaptive = item.get("adaptiveWorkout")
                if isinstance(adaptive, dict):
                    workout_id = adaptive.get("workoutId")
            if workout_id is None:
                continue

            workout_id_str = str(workout_id).strip()
            if not workout_id_str or workout_id_str in seen_ids:
                continue
            seen_ids.add(workout_id_str)

            workouts.append(
                {
                    "workout_id": workout_id_str,
                    "title": str(item.get("title") or "").strip(),
                    "date": item_date,
                    "sport_type_key": str(item.get("sportTypeKey") or "").strip().lower(),
                    "item_type": str(item.get("itemType") or "").strip(),
                }
            )
        return workouts

    def find_matching_workout_ids(
        self,
        *,
        target_date: date,
        workout_name: str,
        sport_type: str | None = None,
    ) -> List[str]:
        normalized_title = workout_name.strip().lower()
        normalized_sport = str(sport_type or "").strip().lower()
        sport_key = (
            SPORT_TYPE_MAP.get(normalized_sport, {}).get("sportTypeKey", "")
            if normalized_sport
            else ""
        )

        matches: List[str] = []
        for item in self.list_scheduled_workouts_for_date(target_date):
            title = str(item.get("title") or "").strip().lower()
            if title != normalized_title:
                continue
            if sport_key:
                # Garmin calendar metadata can drift (empty or wrong sport_type_key) even when
                # the title is exact. Prefer title+date identity for dedupe safety.
                pass
            matches.append(str(item.get("workout_id")))
        return matches

    def schedule_workout(
        self,
        workout_id: str,
        target_date: date,
    ) -> bool:
        payload = {"date": target_date.isoformat()}
        endpoint = f"/workout-service/schedule/{int(workout_id)}"
        try:
            resp = self.garth.connectapi(endpoint, method="POST", json=payload)
        except Exception:
            return False
        if isinstance(resp, dict):
            if resp.get("workoutScheduleId"):
                return True
            if resp.get("id") or resp.get("scheduleId"):
                return True
            if resp.get("workoutId") == int(workout_id):
                return True
            if isinstance(resp.get("message"), str) and "already" in resp.get("message", "").lower():
                return True
            return False
        return True

    def delete_workout(self, workout_id: str) -> bool:
        resp = self.garth.request(
            "DELETE", "connectapi", f"/workout-service/workout/{workout_id}", api=True
        )
        return not (hasattr(resp, "status_code") and resp.status_code >= 400)

    def create_and_schedule(
        self,
        name: str,
        sport_type: str,
        steps: List[Dict[str, Any]],
        target_date: date,
        description: str = "",
    ) -> Optional[str]:
        result = self.create_workout(name, sport_type, steps, description)
        if not result:
            return None

        workout_id = str(result.get("workoutId", ""))
        if workout_id and self.schedule_workout(workout_id, target_date):
            return workout_id

        if workout_id:
            self.delete_workout(workout_id)
        return None
