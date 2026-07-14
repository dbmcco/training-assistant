from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]


def test_scheduler_points_only_at_training_assistant_worker():
    plist = (ROOT / "../deploy/com.training.garmin-sync.plist").resolve().read_text()
    assert "training-assistant/api/scripts/run_garmin_sync.sh" in plist
    assert "StartInterval" in plist


def test_runner_is_shell_valid_and_points_at_internal_cli():
    runner = ROOT / "scripts/run_garmin_sync.sh"
    result = subprocess.run(["bash", "-n", str(runner)], capture_output=True, text=True)
    assert result.returncode == 0
    contents = runner.read_text()
    assert "scripts/garmin_sync.py" in contents
    assert 'API_DIR="$ROOT_DIR/api"' in contents
