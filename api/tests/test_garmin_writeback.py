from pathlib import Path
from unittest.mock import MagicMock, patch
import json

from src.config import settings
from src.services.garmin_writeback import (
    _discipline_matches,
    _run_writeback,
    _workout_matches,
    _run_writeback_with_verify,
    verify_writeback,
)


def test_discipline_matches_known_mappings():
    assert _discipline_matches("running", "running") is True
    assert _discipline_matches("cycling", "cycling") is True
    assert _discipline_matches("swimming", "swimming") is True
    assert _discipline_matches("strength_training", "strength") is True
    assert _discipline_matches("yoga", "flexibility") is True


def test_discipline_matches_case_insensitive():
    assert _discipline_matches("Running", "RUNNING") is True
    assert _discipline_matches("CYCLING", "cycling") is True


def test_discipline_matches_unknown_returns_false():
    assert _discipline_matches("rowing", "running") is False
    assert _discipline_matches("", "running") is False


def test_workout_matches_by_discipline():
    item = {"sport_type_key": "running", "title": "Some Workout", "date": "2026-04-13"}
    assert _workout_matches(item, "running", "easy", "2026-04-13") is True


def test_workout_matches_by_title_fallback():
    item = {
        "sport_type_key": "",
        "title": "Running Easy (2026-04-13)",
        "date": "2026-04-13",
    }
    assert _workout_matches(item, "running", "Easy", "2026-04-13") is True


def test_workout_matches_no_match():
    item = {"sport_type_key": "cycling", "title": "Cycling Tempo", "date": "2026-04-13"}
    assert _workout_matches(item, "running", "easy", "2026-04-13") is False


def test_verify_writeback_timeout(monkeypatch):
    import subprocess as sp

    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)
    monkeypatch.setattr(settings, "garmin_writeback_verify_timeout_seconds", 1)

    def fake_run(*args, **kwargs):
        raise sp.TimeoutExpired(cmd="test", timeout=1)

    with (
        patch(
            "src.services.garmin_writeback._resolve_repo_and_python",
            return_value=(Path("/tmp/fake"), Path("/tmp/fake/python3")),
        ),
        patch("src.services.garmin_writeback.subprocess.run", side_effect=fake_run),
        patch("pathlib.Path.exists", return_value=True),
    ):
        result = verify_writeback(
            workout_date="2026-04-13",
            discipline="running",
            workout_type="easy",
            timeout_seconds=1,
        )

    assert result["verified"] is False
    assert result["error"] == "verification_timeout"


def test_verify_writeback_repo_not_found(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)

    with patch(
        "src.services.garmin_writeback._resolve_repo_and_python",
        return_value=(Path("/nonexistent"), Path("/nonexistent/py")),
    ):
        result = verify_writeback(
            workout_date="2026-04-13",
            discipline="running",
            workout_type="easy",
        )

    assert result["verified"] is False
    assert result["error"] == "garmin_repo_or_python_not_found"


def test_verify_writeback_no_matching_workout(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)
    monkeypatch.setattr(settings, "garmin_writeback_verify_timeout_seconds", 5)

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = '{"status": "success", "workouts": [{"workout_id": "123", "title": "Cycling Tempo", "sport_type_key": "cycling", "date": "2026-04-13"}]}'
    mock_proc.stderr = ""

    with (
        patch(
            "src.services.garmin_writeback._resolve_repo_and_python",
            return_value=(Path("/tmp/fake"), Path("/tmp/fake/python3")),
        ),
        patch("src.services.garmin_writeback.subprocess.run", return_value=mock_proc),
        patch("pathlib.Path.exists", return_value=True),
    ):
        result = verify_writeback(
            workout_date="2026-04-13",
            discipline="running",
            workout_type="easy",
        )

    assert result["verified"] is False
    assert "no_matching_workout_found" in result["error"]


def test_verify_writeback_found_matching_workout(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)
    monkeypatch.setattr(settings, "garmin_writeback_verify_timeout_seconds", 5)

    match_item = {
        "workout_id": "456",
        "title": "Running Easy (2026-04-13)",
        "sport_type_key": "running",
        "date": "2026-04-13",
    }
    decoy_item = {
        "workout_id": "123",
        "title": "Cycling Tempo",
        "sport_type_key": "cycling",
        "date": "2026-04-13",
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(
        {"status": "success", "workouts": [decoy_item, match_item]}
    )
    mock_proc.stderr = ""

    with (
        patch(
            "src.services.garmin_writeback._resolve_repo_and_python",
            return_value=(Path("/tmp/fake"), Path("/tmp/fake/python3")),
        ),
        patch("src.services.garmin_writeback.subprocess.run", return_value=mock_proc),
        patch("pathlib.Path.exists", return_value=True),
    ):
        result = verify_writeback(
            workout_date="2026-04-13",
            discipline="running",
            workout_type="easy",
        )

    assert result["verified"] is True
    assert result["match_details"]["workout_id"] == "456"
    assert result["error"] is None


def test_run_writeback_with_verify_failed_writeback(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)

    with patch(
        "src.services.garmin_writeback._run_writeback",
        return_value={
            "status": "failed",
            "returncode": 1,
            "stderr": "some error",
        },
    ):
        result = _run_writeback_with_verify(
            {"workout_date": "2026-04-13", "discipline": "running"}
        )

    assert result["verification_status"] == "failed"


def test_run_writeback_with_verify_skipped(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)

    with patch(
        "src.services.garmin_writeback._run_writeback",
        return_value={
            "status": "skipped",
            "reason": "garmin_writeback_disabled",
        },
    ):
        result = _run_writeback_with_verify(
            {"workout_date": "2026-04-13", "discipline": "running"}
        )

    assert result["verification_status"] == "skipped"


def test_run_writeback_with_verify_success(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)

    with (
        patch(
            "src.services.garmin_writeback._run_writeback",
            return_value={
                "status": "success",
                "workout_id": "789",
            },
        ),
        patch(
            "src.services.garmin_writeback.verify_writeback",
            return_value={
                "verified": True,
                "match_details": {
                    "workout_id": "789",
                    "title": "Running Easy (2026-04-13)",
                },
                "error": None,
            },
        ),
    ):
        result = _run_writeback_with_verify(
            {
                "workout_date": "2026-04-13",
                "discipline": "running",
                "workout_type": "easy",
            }
        )

    assert result["verification_status"] == "success"
    assert result["verification_details"]["workout_id"] == "789"


def test_run_writeback_with_verify_unverified(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)

    with (
        patch(
            "src.services.garmin_writeback._run_writeback",
            return_value={
                "status": "success",
                "workout_id": "789",
            },
        ),
        patch(
            "src.services.garmin_writeback.verify_writeback",
            return_value={
                "verified": False,
                "match_details": None,
                "error": "no_matching_workout_found",
            },
        ),
    ):
        result = _run_writeback_with_verify(
            {
                "workout_date": "2026-04-13",
                "discipline": "running",
                "workout_type": "easy",
            }
        )

    assert result["verification_status"] == "synced_unverified"
    assert result["verification_error"] == "no_matching_workout_found"


def test_run_writeback_with_verify_disabled(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", False)

    with patch(
        "src.services.garmin_writeback._run_writeback",
        return_value={
            "status": "success",
            "workout_id": "789",
        },
    ):
        result = _run_writeback_with_verify(
            {
                "workout_date": "2026-04-13",
                "discipline": "running",
                "workout_type": "easy",
            }
        )

    assert result["verification_status"] == "success"


def test_run_writeback_with_verify_exception_resilient(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)
    monkeypatch.setattr(settings, "garmin_writeback_verify_delay_seconds", 0)

    with (
        patch(
            "src.services.garmin_writeback._run_writeback",
            return_value={
                "status": "success",
                "workout_id": "789",
            },
        ),
        patch(
            "src.services.garmin_writeback.verify_writeback",
            side_effect=RuntimeError("auth failure"),
        ),
    ):
        result = _run_writeback_with_verify(
            {
                "workout_date": "2026-04-13",
                "discipline": "running",
                "workout_type": "easy",
            }
        )

    assert result["verification_status"] == "synced_unverified"
    assert "auth failure" in result["verification_error"]


def test_run_writeback_with_verify_missing_date_discipline(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_verify_enabled", True)

    with patch(
        "src.services.garmin_writeback._run_writeback",
        return_value={
            "status": "success",
            "workout_id": "789",
        },
    ):
        result = _run_writeback_with_verify({})

    assert result["verification_status"] == "synced_unverified"
    assert (
        result["verification_error"] == "missing_workout_date_or_discipline_for_verify"
    )


def test_no_default_success_status(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_enabled", True)

    repo = Path("/tmp/fake_garmin")
    python = repo / ".venv" / "bin" / "python3"
    script = repo / "apply_plan_change.py"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = '{"workout_id": "123"}'
    mock_proc.stderr = ""

    with (
        patch(
            "src.services.garmin_writeback._resolve_repo_and_python",
            return_value=(repo, python),
        ),
        patch("src.services.garmin_writeback.subprocess.run", return_value=mock_proc),
        patch("pathlib.Path.exists", return_value=True),
        patch(
            "src.services.garmin_writeback.verify_writeback",
            return_value={"verified": True, "match_details": {}, "error": None},
        ),
        patch.object(settings, "garmin_writeback_verify_enabled", False),
    ):
        result = _run_writeback_with_verify(
            {
                "workout_date": "2026-04-13",
                "discipline": "running",
                "workout_type": "easy",
            }
        )

    assert result.get("status") is None


def test_run_writeback_passes_sync_database_url_to_subprocess(monkeypatch):
    monkeypatch.setattr(settings, "garmin_writeback_enabled", True)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://sync")

    repo = Path("/tmp/fake_garmin")
    python = repo / ".venv" / "bin" / "python3"
    captured = {}

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = '{"status": "success", "workout_id": "123"}'
    mock_proc.stderr = ""

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env")
        return mock_proc

    with (
        patch(
            "src.services.garmin_writeback._resolve_repo_and_python",
            return_value=(repo, python),
        ),
        patch("src.services.garmin_writeback.subprocess.run", side_effect=fake_run),
        patch("pathlib.Path.exists", return_value=True),
    ):
        result = _run_writeback(
            {
                "workout_date": "2026-04-13",
                "discipline": "running",
                "workout_type": "easy",
            }
        )

    assert result["status"] == "success"
    assert captured["env"]["DATABASE_URL"] == "postgresql://sync"
