"""Garmin plan writeback bridge.

Uses the sibling garmin-connect-sync project to write workout adjustments
back to Garmin Connect via its authenticated tooling.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from src.config import settings


def _default_garmin_repo() -> Path:
    # .../training-assistant/api/src/services -> .../experiments
    experiments_root = Path(__file__).resolve().parents[4]
    return experiments_root / "garmin-connect-sync"


def _resolve_repo_and_python() -> tuple[Path, Path]:
    repo = (
        Path(settings.garmin_writeback_repo).expanduser()
        if settings.garmin_writeback_repo
        else _default_garmin_repo()
    )
    python_bin = (
        Path(settings.garmin_writeback_python).expanduser()
        if settings.garmin_writeback_python
        else repo / ".venv" / "bin" / "python3"
    )
    return repo, python_bin


def _garmin_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    sync_database_url = env.get("DATABASE_URL_SYNC")
    if sync_database_url:
        env["DATABASE_URL"] = sync_database_url
    return env


def _run_writeback(payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.garmin_writeback_enabled:
        return {"status": "skipped", "reason": "garmin_writeback_disabled"}

    repo, python_bin = _resolve_repo_and_python()
    script = repo / "apply_plan_change.py"

    if not repo.exists():
        return {"status": "failed", "reason": f"garmin_repo_not_found:{repo}"}
    if not script.exists():
        return {
            "status": "failed",
            "reason": f"garmin_writeback_script_missing:{script}",
        }
    if not python_bin.exists():
        return {"status": "failed", "reason": f"garmin_python_missing:{python_bin}"}

    cmd = [
        str(python_bin),
        str(script),
        "--payload-json",
        json.dumps(payload),
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env=_garmin_subprocess_env(),
    )

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    parsed_stdout: dict[str, Any] | None = None
    if stdout:
        try:
            parsed_stdout = json.loads(stdout)
        except json.JSONDecodeError:
            parsed_stdout = {"raw": stdout}

    if proc.returncode != 0:
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "stdout": parsed_stdout or stdout,
            "stderr": stderr,
        }

    if parsed_stdout and isinstance(parsed_stdout, dict):
        return parsed_stdout

    return {"status": "success", "stdout": stdout, "stderr": stderr}


_VERIFY_SCRIPT = (
    "import json, sys\n"
    "from garmin_writer import GarminWriter\n"
    "from sync import GarminSyncClient\n"
    "sync = GarminSyncClient()\n"
    "try:\n"
    "    writer = GarminWriter(sync.client)\n"
    "    target_date = __import__('datetime').date.fromisoformat(sys.argv[1])\n"
    "    workouts = writer.list_scheduled_workouts_for_date(target_date)\n"
    "    print(json.dumps({'status': 'success', 'workouts': workouts}))\n"
    "except Exception as e:\n"
    "    print(json.dumps({'status': 'error', 'error': str(e)}))\n"
    "    sys.exit(1)\n"
    "finally:\n"
    "    sync.close()\n"
)


def _discipline_matches(sport_type_key: str, discipline: str) -> bool:
    mapping = {
        "running": "running",
        "cycling": "cycling",
        "swimming": "swimming",
        "strength_training": "strength",
        "yoga": "flexibility",
    }
    return mapping.get(sport_type_key.lower()) == discipline.lower()


def _workout_matches(
    item: dict[str, Any], discipline: str, workout_type: str, workout_date: str
) -> bool:
    sport_key = str(item.get("sport_type_key") or "").lower()
    if _discipline_matches(sport_key, discipline):
        return True
    title = str(item.get("title") or "").lower()
    expected = f"{discipline.title()} {workout_type}".lower()
    return expected in title


def verify_writeback(
    *,
    workout_date: str,
    discipline: str,
    workout_type: str,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Confirm a workout landed in Garmin after writing.

    Returns {"verified": bool, "match_details": dict|null, "error": str|null}
    """
    timeout = timeout_seconds or settings.garmin_writeback_verify_timeout_seconds
    repo, python_bin = _resolve_repo_and_python()

    if not repo.exists() or not python_bin.exists():
        return {
            "verified": False,
            "match_details": None,
            "error": "garmin_repo_or_python_not_found",
        }

    delay = settings.garmin_writeback_verify_delay_seconds
    if delay > 0:
        time.sleep(min(delay, 3))

    cmd = [
        str(python_bin),
        "-c",
        _VERIFY_SCRIPT,
        workout_date,
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_garmin_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        return {
            "verified": False,
            "match_details": None,
            "error": "verification_timeout",
        }

    stdout = proc.stdout.strip()
    if proc.returncode != 0 or not stdout:
        err = proc.stderr.strip()[-500:] if proc.stderr.strip() else "unknown"
        return {
            "verified": False,
            "match_details": None,
            "error": f"verify_script_error: {err}",
        }

    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "verified": False,
            "match_details": None,
            "error": "verify_output_not_json",
        }

    workouts = result.get("workouts", [])
    for item in workouts:
        if not isinstance(item, dict):
            continue
        if _workout_matches(item, discipline, workout_type, workout_date):
            return {"verified": True, "match_details": item, "error": None}

    return {
        "verified": False,
        "match_details": None,
        "error": f"no_matching_workout_found (date={workout_date}, discipline={discipline}, type={workout_type})",
    }


def _run_writeback_with_verify(payload: dict[str, Any]) -> dict[str, Any]:
    writeback_result = _run_writeback(payload)

    if writeback_result.get("status") == "failed":
        writeback_result["verification_status"] = "failed"
        return writeback_result

    if writeback_result.get("status") == "skipped":
        writeback_result["verification_status"] = "skipped"
        return writeback_result

    if not settings.garmin_writeback_verify_enabled:
        status = (
            "success"
            if writeback_result.get("status") == "success"
            else "synced_unverified"
        )
        writeback_result["verification_status"] = status
        return writeback_result

    workout_date = str(payload.get("workout_date") or "")
    discipline = str(payload.get("discipline") or "")
    workout_type = str(payload.get("workout_type") or "")

    if not workout_date or not discipline:
        writeback_result["verification_status"] = "synced_unverified"
        writeback_result["verification_error"] = (
            "missing_workout_date_or_discipline_for_verify"
        )
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
    """Async wrapper around the external Garmin writeback command.

    Runs writeback immediately. If verification is enabled, spawns a
    background verification task so the caller is not blocked by the
    verify delay + subprocess.  The initial result carries
    verification_status='synced_unverified'; the background task
    updates the returned dict in-place with the real verification
    outcome once it completes (callers that persist the result to DB
    should re-read or accept the initial status).
    """
    writeback_result = await asyncio.to_thread(_run_writeback, payload)

    if writeback_result.get("status") in ("failed", "skipped"):
        writeback_result["verification_status"] = writeback_result["status"]
        return writeback_result

    if not settings.garmin_writeback_verify_enabled:
        status = (
            "success"
            if writeback_result.get("status") == "success"
            else "synced_unverified"
        )
        writeback_result["verification_status"] = status
        return writeback_result

    workout_date = str(payload.get("workout_date") or "")
    discipline = str(payload.get("discipline") or "")
    workout_type = str(payload.get("workout_type") or "")

    if not workout_date or not discipline:
        writeback_result["verification_status"] = "synced_unverified"
        writeback_result["verification_error"] = (
            "missing_workout_date_or_discipline_for_verify"
        )
        return writeback_result

    writeback_result["verification_status"] = "synced_unverified"

    async def _bg_verify():
        try:
            await asyncio.sleep(min(settings.garmin_writeback_verify_delay_seconds, 3))
            verification = await asyncio.to_thread(
                verify_writeback,
                workout_date=workout_date,
                discipline=discipline,
                workout_type=workout_type,
                timeout_seconds=min(
                    settings.garmin_writeback_verify_timeout_seconds, 8
                ),
            )
            if verification.get("verified"):
                writeback_result["verification_status"] = "success"
                writeback_result["verification_details"] = verification.get(
                    "match_details"
                )
            else:
                writeback_result["verification_error"] = verification.get("error")
        except Exception as exc:
            writeback_result["verification_error"] = f"verify_exception: {exc}"

    try:
        asyncio.get_running_loop().create_task(_bg_verify())
    except RuntimeError:
        pass

    return writeback_result


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
    """Build a deterministic payload for external writeback tooling."""
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
