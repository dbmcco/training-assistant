from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[2]
FORBIDDEN = "garmin-" + "connect-sync"


def _text_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            yield path


def test_active_training_assistant_files_do_not_reference_legacy_repo():
    roots = [
        REPOSITORY_ROOT / "api/src",
        REPOSITORY_ROOT / "api/scripts",
        REPOSITORY_ROOT / "api/tests",
        REPOSITORY_ROOT / "deploy",
        REPOSITORY_ROOT / "README.md",
        REPOSITORY_ROOT / "docs/superpowers/runbooks",
    ]
    hits = [
        str(path.relative_to(REPOSITORY_ROOT))
        for root in roots
        for path in _text_files(root)
        if FORBIDDEN in path.read_text(errors="ignore")
    ]
    assert hits == []


# garminconnect client methods the sync engine used to call but never existed —
# each produced a silent AttributeError warning every sync run.
DEAD_CLIENT_METHODS = (
    "get_intensity_minutes_data",
    "get_body_battery_events",
    "get_morning_training_readiness",
)


def test_no_dead_garmin_client_methods_in_production_code():
    """Guard against re-introducing garminconnect method names that do not exist.

    Production code (src + scripts) must not reference these; they silently warn
    and skip the metric every run. Intensity minutes are sourced from the user
    summary instead (see intensity_minutes_from_summary).
    """
    roots = [
        REPOSITORY_ROOT / "api/src",
        REPOSITORY_ROOT / "api/scripts",
    ]
    hits = [
        f"{path.relative_to(REPOSITORY_ROOT)}:{name}"
        for root in roots
        for path in _text_files(root)
        for name in DEAD_CLIENT_METHODS
        if name in path.read_text(errors="ignore")
    ]
    assert hits == [], f"dead garminconnect method names re-introduced: {hits}"
