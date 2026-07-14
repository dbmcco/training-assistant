"""Garmin workout writeback through the internal Training Assistant integration."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

from src.config import settings
from src.integrations.garmin.config import GarminIntegrationSettings
from src.integrations.garmin.sync_engine import GarminSyncClient
from src.integrations.garmin.workouts import GarminWorkoutWriter


def _resolve_repo_and_python() -> tuple[Path, Path]:
    """Compatibility helper returning the internal integration boundary."""
    integration_root = Path(__file__).resolve().parents[1] / "integrations" / "garmin"
    return integration_root, Path(sys.executable)


def _run_writeback(payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.garmin_writeback_enabled:
        return {"status": "skipped", "reason": "garmin_writeback_disabled"}

    sync_client: GarminSyncClient | None = None
    writer: GarminWorkoutWriter | None = None
    try:
        integration_settings = GarminIntegrationSettings.from_app_settings()
        sync_client = GarminSyncClient(integration_settings)
        writer = GarminWorkoutWriter(sync_client)
        return writer.apply_change(payload)
    except Exception as exc:
        return {"status": "failed", "reason": "garmin_writeback_failed", "error": str(exc)}
    finally:
        if writer is not None:
            writer.close()
        elif sync_client is not None:
            sync_client.close()


def _discipline_matches(sport_type_key: str, discipline: str) -> bool:
    mapping = {
        "running": {"running", "run"},
        "cycling": {"cycling", "bike"},
        "swimming": {"swimming", "swim", "lap_swimming"},
        "strength_training": {"strength", "strength_training"},
        "yoga": {"flexibility", "yoga"},
    }
    return discipline.lower() in mapping.get(sport_type_key.lower(), set())


def _workout_matches(
    item: dict[str, Any], discipline: str, workout_type: str, workout_date: str
) -> bool:
    sport_key = str(item.get("sport_type_key") or "").lower()
    if _discipline_matches(sport_key, discipline):
        return True
    title = str(item.get("title") or "").lower()
    expected = f"{discipline.title()} {workout_type}".lower()
    return expected in title and str(item.get("date") or workout_date) == workout_date


def verify_writeback(
    *,
    workout_date: str,
    discipline: str,
    workout_type: str,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Confirm a workout landed in Garmin after writing."""
    _ = timeout_seconds or settings.garmin_writeback_verify_timeout_seconds
    if settings.garmin_writeback_verify_delay_seconds > 0:
        time.sleep(min(settings.garmin_writeback_verify_delay_seconds, 3))

    sync_client: GarminSyncClient | None = None
    writer: GarminWorkoutWriter | None = None
    try:
        integration_settings = GarminIntegrationSettings.from_app_settings()
        sync_client = GarminSyncClient(integration_settings)
        writer = GarminWorkoutWriter(sync_client)
        workouts = writer.scheduled_workouts(
            __import__("datetime").date.fromisoformat(workout_date)
        )
        for item in workouts:
            if isinstance(item, dict) and _workout_matches(item, discipline, workout_type, workout_date):
                return {"verified": True, "match_details": item, "error": None}
        return {
            "verified": False,
            "match_details": None,
            "error": f"no_matching_workout_found (date={workout_date}, discipline={discipline}, type={workout_type})",
        }
    except TimeoutError:
        return {"verified": False, "match_details": None, "error": "verification_timeout"}
    except Exception as exc:
        return {"verified": False, "match_details": None, "error": f"verify_exception: {exc}"}
    finally:
        if writer is not None:
            writer.close()
        elif sync_client is not None:
            sync_client.close()


def _run_writeback_with_verify(payload: dict[str, Any]) -> dict[str, Any]:
    writeback_result = _run_writeback(payload)
    if writeback_result.get("status") in {"failed", "skipped"}:
        writeback_result["verification_status"] = writeback_result["status"]
        return writeback_result

    if not settings.garmin_writeback_verify_enabled:
        writeback_result["verification_status"] = "success"
        return writeback_result

    workout_date = str(payload.get("workout_date") or "")
    discipline = str(payload.get("discipline") or "")
    workout_type = str(payload.get("workout_type") or "")
    if not workout_date or not discipline:
        writeback_result["verification_status"] = "synced_unverified"
        writeback_result["verification_error"] = "missing_workout_date_or_discipline_for_verify"
        return writeback_result

    try:
        verification = verify_writeback(
            workout_date=workout_date,
            discipline=discipline,
            workout_type=workout_type,
        )
    except Exception as exc:
        writeback_result["verification_status"] = "synced_unverified"
        writeback_result["verification_error"] = f"verify_exception: {exc}"
        return writeback_result

    if verification.get("verified"):
        writeback_result["verification_status"] = "success"
        writeback_result["verification_details"] = verification.get("match_details")
    else:
        writeback_result["verification_status"] = "synced_unverified"
        writeback_result["verification_error"] = verification.get("error")
    return writeback_result


async def write_recommendation_change(payload: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(_run_writeback_with_verify, payload)


def fallback_writeback_payload(
    *,
    workout_date: str | None,
    discipline: str | None,
    workout_type: str | None,
    target_duration: int | None,
    description: str | None,
    workout_steps: list[dict[str, Any]] | None = None,
    replace_workout_id: str | None = None,
    dedupe_by_title: bool = True,
    recommendation_text: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "workout_date": workout_date,
        "discipline": discipline,
        "workout_type": workout_type,
        "target_duration": target_duration,
        "description": description,
        "replace_workout_id": replace_workout_id,
        "dedupe_by_title": dedupe_by_title,
        "recommendation_text": recommendation_text,
        "source": "training-assistant",
        "python": sys.executable,
    }
    if workout_steps:
        payload["workout_steps"] = workout_steps
    return payload
