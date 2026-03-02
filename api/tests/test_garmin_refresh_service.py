from pathlib import Path

from src.config import settings
from src.services.garmin_refresh import _refresh_dashboard_data


def _prepare_fake_runtime(tmp_path: Path, monkeypatch):
    repo = tmp_path / "garmin-sync"
    repo.mkdir()
    sync_script = repo / "sync.py"
    sync_script.write_text("#!/usr/bin/env python3\n")

    python_bin = tmp_path / "python3"
    python_bin.write_text("#!/usr/bin/env python3\n")

    monkeypatch.setattr(
        "src.services.garmin_refresh._resolve_repo_and_python",
        lambda: (repo, python_bin),
    )
    monkeypatch.setattr("src.services.garmin_refresh._acquire_lock", lambda: True)
    monkeypatch.setattr("src.services.garmin_refresh._release_lock", lambda: None)
    monkeypatch.setattr(
        "src.services.garmin_refresh._load_last_success_epoch",
        lambda: None,
    )
    monkeypatch.setattr(
        "src.services.garmin_refresh._store_last_success_epoch",
        lambda _epoch: None,
    )


def test_refresh_uses_configured_days_back(tmp_path, monkeypatch):
    _prepare_fake_runtime(tmp_path, monkeypatch)
    captured: list[list[str]] = []

    def fake_run_cmd(cmd: list[str], cwd: Path, timeout_seconds: int):
        captured.append(cmd)
        return {"status": "success", "command": cmd}

    monkeypatch.setattr("src.services.garmin_refresh._run_cmd", fake_run_cmd)
    monkeypatch.setattr(settings, "garmin_refresh_enabled", True)
    monkeypatch.setattr(settings, "garmin_refresh_timeout_seconds", 30)
    monkeypatch.setattr(settings, "garmin_refresh_min_interval_seconds", 0)
    monkeypatch.setattr(settings, "garmin_refresh_days_back", 2)

    result = _refresh_dashboard_data(force=True)

    assert result["status"] == "success"
    assert result["days_back"] == 2
    assert captured[0][-2:] == ["--days-back", "2"]


def test_refresh_clamps_negative_days_back(tmp_path, monkeypatch):
    _prepare_fake_runtime(tmp_path, monkeypatch)
    captured: list[list[str]] = []

    def fake_run_cmd(cmd: list[str], cwd: Path, timeout_seconds: int):
        captured.append(cmd)
        return {"status": "success", "command": cmd}

    monkeypatch.setattr("src.services.garmin_refresh._run_cmd", fake_run_cmd)
    monkeypatch.setattr(settings, "garmin_refresh_enabled", True)
    monkeypatch.setattr(settings, "garmin_refresh_timeout_seconds", 30)
    monkeypatch.setattr(settings, "garmin_refresh_min_interval_seconds", 0)
    monkeypatch.setattr(settings, "garmin_refresh_days_back", -5)

    result = _refresh_dashboard_data(force=True)

    assert result["status"] == "success"
    assert result["days_back"] == 0
    assert captured[0][-2:] == ["--days-back", "0"]
