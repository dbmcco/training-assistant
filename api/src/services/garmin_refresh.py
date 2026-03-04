"""On-demand Garmin refresh bridge for dashboard loads.

Runs lightweight garmin-connect-sync commands so app refreshes can pull fresh
daily recovery metrics (sleep/HRV/readiness) without requiring hourly cron.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from src.config import settings

LOCK_DIR = Path("/tmp/training-assistant-garmin-refresh.lock")
PID_FILE = LOCK_DIR / "pid"
STATE_FILE = Path("/tmp/training-assistant-garmin-refresh-state.json")


def _assistant_mode() -> bool:
    return settings.plan_ownership_mode.strip().lower() == "assistant"


def _default_garmin_repo() -> Path:
    # .../training-assistant/api/src/services -> .../experiments
    experiments_root = Path(__file__).resolve().parents[4]
    return experiments_root / "garmin-connect-sync"


def _resolve_repo_and_python() -> tuple[Path, Path]:
    if settings.garmin_refresh_repo:
        repo = Path(settings.garmin_refresh_repo).expanduser()
    elif settings.garmin_writeback_repo:
        repo = Path(settings.garmin_writeback_repo).expanduser()
    else:
        repo = _default_garmin_repo()

    if settings.garmin_refresh_python:
        python_bin = Path(settings.garmin_refresh_python).expanduser()
    elif settings.garmin_writeback_python:
        python_bin = Path(settings.garmin_writeback_python).expanduser()
    else:
        python_bin = repo / ".venv" / "bin" / "python3"

    return repo, python_bin


def _load_last_success_epoch() -> float | None:
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    raw = data.get("last_success_epoch")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _store_last_success_epoch(epoch: float) -> None:
    payload = {"last_success_epoch": epoch}
    STATE_FILE.write_text(json.dumps(payload))


def _lock_age_seconds() -> float | None:
    try:
        return max(0.0, time.time() - LOCK_DIR.stat().st_mtime)
    except OSError:
        return None


def _lock_is_stale() -> bool:
    lock_age = _lock_age_seconds()
    stale_after = max(settings.garmin_refresh_timeout_seconds, 5) + 15
    if lock_age is not None and lock_age > stale_after:
        return True

    if not PID_FILE.exists():
        return True
    try:
        pid = int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return True
    try:
        os.kill(pid, 0)
        return False
    except OSError:
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


def _run_cmd(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raw_stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        raw_stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "status": "failed",
            "returncode": None,
            "reason": "timeout",
            "timeout_seconds": timeout_seconds,
            "stdout": raw_stdout.strip()[-2000:],
            "stderr": raw_stderr.strip()[-2000:],
            "command": cmd,
        }
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if proc.returncode != 0:
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "stdout": stdout[-2000:] if stdout else "",
            "stderr": stderr[-2000:] if stderr else "",
            "command": cmd,
        }
    return {
        "status": "success",
        "stdout": stdout[-2000:] if stdout else "",
        "stderr": stderr[-2000:] if stderr else "",
        "command": cmd,
    }


def _refresh_dashboard_data(*, include_calendar: bool = False, force: bool = False) -> dict[str, Any]:
    if not settings.garmin_refresh_enabled:
        return {"status": "skipped", "reason": "garmin_refresh_disabled"}

    repo, python_bin = _resolve_repo_and_python()
    sync_script = repo / "sync.py"

    if not repo.exists():
        return {"status": "failed", "reason": f"garmin_repo_not_found:{repo}"}
    if not sync_script.exists():
        return {"status": "failed", "reason": f"garmin_sync_script_missing:{sync_script}"}
    if not python_bin.exists():
        return {"status": "failed", "reason": f"garmin_python_missing:{python_bin}"}

    now_epoch = time.time()
    min_interval = max(settings.garmin_refresh_min_interval_seconds, 0)
    last_success = _load_last_success_epoch()
    if (
        not force
        and min_interval > 0
        and last_success is not None
        and (now_epoch - last_success) < min_interval
    ):
        return {
            "status": "skipped",
            "reason": "min_interval_not_elapsed",
            "seconds_since_last_success": round(now_epoch - last_success, 1),
            "min_interval_seconds": min_interval,
        }

    if not _acquire_lock():
        lock_age = _lock_age_seconds()
        return {
            "status": "skipped",
            "reason": "refresh_already_running",
            "lock_age_seconds": round(lock_age, 1) if lock_age is not None else None,
        }

    timeout_seconds = max(settings.garmin_refresh_timeout_seconds, 5)
    days_back = max(settings.garmin_refresh_days_back, 0)
    include_calendar_requested = include_calendar
    calendar_skipped_reason: str | None = None
    if include_calendar and _assistant_mode():
        include_calendar = False
        calendar_skipped_reason = "assistant_owned_plan_mode"
    try:
        commands: list[list[str]] = [
            [str(python_bin), str(sync_script), "--daily-only", "--days-back", str(days_back)],
        ]
        if include_calendar:
            commands.append([str(python_bin), str(sync_script), "--calendar-only"])

        results: list[dict[str, Any]] = []
        for cmd in commands:
            cmd_result = _run_cmd(cmd, cwd=repo, timeout_seconds=timeout_seconds)
            results.append(cmd_result)
            if cmd_result.get("status") != "success":
                return {
                    "status": "failed",
                    "reason": "sync_command_failed",
                    "results": results,
                }

        _store_last_success_epoch(time.time())
        return {
            "status": "success",
            "include_calendar": include_calendar,
            "include_calendar_requested": include_calendar_requested,
            "calendar_skipped_reason": calendar_skipped_reason,
            "days_back": days_back,
            "results": results,
        }
    finally:
        _release_lock()


async def refresh_garmin_daily_data_on_demand(
    *, include_calendar: bool = False, force: bool = False
) -> dict[str, Any]:
    """Refresh Garmin data from garmin-connect-sync during app refresh."""
    return await asyncio.to_thread(
        _refresh_dashboard_data,
        include_calendar=include_calendar,
        force=force,
    )
