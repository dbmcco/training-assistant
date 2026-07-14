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
