from __future__ import annotations

import shutil
from pathlib import Path


class GarminSyncLock:
    """Simple cross-process lock for scheduled and on-demand Garmin runs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._held = False

    def acquire(self) -> None:
        try:
            self.path.mkdir(parents=True)
            self._held = True
        except FileExistsError as exc:
            raise RuntimeError(f"Garmin sync already running: {self.path}") from exc

    def release(self) -> None:
        if self._held:
            shutil.rmtree(self.path, ignore_errors=True)
            self._held = False

    def __enter__(self) -> "GarminSyncLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()
