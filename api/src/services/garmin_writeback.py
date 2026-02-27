"""Garmin plan writeback bridge.

Uses the sibling garmin-connect-sync project to write workout adjustments
back to Garmin Connect via its authenticated tooling.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.config import settings


def _default_garmin_repo() -> Path:
    # .../training-assistant/api/src/services -> .../experiments
    experiments_root = Path(__file__).resolve().parents[4]
    return experiments_root / "garmin-connect-sync"


def _resolve_repo_and_python() -> tuple[Path, Path]:
    repo = Path(settings.garmin_writeback_repo).expanduser() if settings.garmin_writeback_repo else _default_garmin_repo()
    python_bin = Path(settings.garmin_writeback_python).expanduser() if settings.garmin_writeback_python else repo / ".venv" / "bin" / "python3"
    return repo, python_bin


def _run_writeback(payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.garmin_writeback_enabled:
        return {"status": "skipped", "reason": "garmin_writeback_disabled"}

    repo, python_bin = _resolve_repo_and_python()
    script = repo / "apply_plan_change.py"

    if not repo.exists():
        return {"status": "failed", "reason": f"garmin_repo_not_found:{repo}"}
    if not script.exists():
        return {"status": "failed", "reason": f"garmin_writeback_script_missing:{script}"}
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
        parsed_stdout.setdefault("status", "success")
        return parsed_stdout

    return {"status": "success", "stdout": stdout, "stderr": stderr}


async def write_recommendation_change(payload: dict[str, Any]) -> dict[str, Any]:
    """Async wrapper around the external Garmin writeback command."""
    return await asyncio.to_thread(_run_writeback, payload)


def fallback_writeback_payload(
    *,
    workout_date: str | None,
    discipline: str | None,
    workout_type: str | None,
    target_duration: int | None,
    description: str | None,
    recommendation_text: str | None,
) -> dict[str, Any]:
    """Build a deterministic payload for external writeback tooling."""
    return {
        "workout_date": workout_date,
        "discipline": discipline,
        "workout_type": workout_type,
        "target_duration": target_duration,
        "description": description,
        "recommendation_text": recommendation_text,
        "source": "training-assistant",
        "python": sys.executable,
    }
