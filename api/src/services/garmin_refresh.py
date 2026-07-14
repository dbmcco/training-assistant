"""On-demand Garmin refresh using the Training Assistant-owned worker."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from src.config import settings
from src.integrations.garmin.config import GarminIntegrationSettings
from src.integrations.garmin.worker import GarminWorker, GarminWorkerArgs

LOCK_DIR = Path("/tmp/training-assistant-garmin-refresh.lock")
PID_FILE = LOCK_DIR / "pid"
STATE_FILE = Path("/tmp/training-assistant-garmin-refresh-state.json")


def _load_last_success_epoch() -> float | None:
    if not STATE_FILE.exists():
        return None
    try:
        raw = json.loads(STATE_FILE.read_text()).get("last_success_epoch")
        return float(raw) if raw is not None else None
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _store_last_success_epoch(epoch: float) -> None:
    STATE_FILE.write_text(json.dumps({"last_success_epoch": epoch}))


def _lock_age_seconds() -> float | None:
    try:
        return max(0.0, time.time() - LOCK_DIR.stat().st_mtime)
    except OSError:
        return None


def _lock_is_stale() -> bool:
    age = _lock_age_seconds()
    if age is not None and age > max(settings.garmin_refresh_timeout_seconds, 5) + 15:
        return True
    if not PID_FILE.exists():
        return True
    try:
        os.kill(int(PID_FILE.read_text().strip()), 0)
        return False
    except (OSError, ValueError):
        return True


def _acquire_lock() -> bool:
    try:
        LOCK_DIR.mkdir()
        PID_FILE.write_text(str(os.getpid()))
        return True
    except FileExistsError:
        if _lock_is_stale():
            shutil.rmtree(LOCK_DIR, ignore_errors=True)
            try:
                LOCK_DIR.mkdir()
                PID_FILE.write_text(str(os.getpid()))
                return True
            except FileExistsError:
                return False
        return False


def _release_lock() -> None:
    shutil.rmtree(LOCK_DIR, ignore_errors=True)


def _run_worker(args: GarminWorkerArgs) -> dict[str, Any]:
    integration_settings = GarminIntegrationSettings.from_app_settings()
    return GarminWorker(integration_settings).run(args)


def _refresh_dashboard_data(*, include_calendar: bool = False, force: bool = False) -> dict[str, Any]:
    if not settings.garmin_refresh_enabled:
        return {"status": "skipped", "reason": "garmin_refresh_disabled"}

    now_epoch = time.time()
    min_interval = max(settings.garmin_refresh_min_interval_seconds, 0)
    last_success = _load_last_success_epoch()
    if (
        not force
        and min_interval > 0
        and last_success is not None
        and now_epoch - last_success < min_interval
    ):
        return {
            "status": "skipped",
            "reason": "min_interval_not_elapsed",
            "seconds_since_last_success": round(now_epoch - last_success, 1),
            "min_interval_seconds": min_interval,
        }

    if not _acquire_lock():
        age = _lock_age_seconds()
        return {
            "status": "skipped",
            "reason": "refresh_already_running",
            "lock_age_seconds": round(age, 1) if age is not None else None,
        }

    try:
        results = [
            _run_worker(
                GarminWorkerArgs(
                    daily_only=True,
                    days_back=max(settings.garmin_refresh_days_back, 0),
                )
            )
        ]
        if results[-1].get("status") == "failed":
            return {"status": "failed", "reason": "sync_command_failed", "results": results}

        if include_calendar:
            results.append(
                _run_worker(
                    GarminWorkerArgs(
                        calendar_only=True,
                        days_back=max(settings.garmin_refresh_days_back, 0),
                    )
                )
            )
            if results[-1].get("status") == "failed":
                return {"status": "failed", "reason": "sync_command_failed", "results": results}

        _store_last_success_epoch(time.time())
        return {
            "status": "success",
            "include_calendar": include_calendar,
            "include_calendar_requested": include_calendar,
            "calendar_skipped_reason": None,
            "days_back": max(settings.garmin_refresh_days_back, 0),
            "results": results,
        }
    finally:
        _release_lock()


async def refresh_garmin_daily_data_on_demand(
    *, include_calendar: bool = False, force: bool = False
) -> dict[str, Any]:
    """Refresh Garmin data without blocking the FastAPI event loop."""
    return await asyncio.to_thread(
        _refresh_dashboard_data,
        include_calendar=include_calendar,
        force=force,
    )
