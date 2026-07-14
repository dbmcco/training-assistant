from __future__ import annotations

import os
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
            (self.path / "pid").write_text(str(os.getpid()))
            self._held = True
            return
        except FileExistsError:
            if not self._is_stale():
                raise RuntimeError(f"Garmin sync already running: {self.path}")
            shutil.rmtree(self.path, ignore_errors=True)
            self.path.mkdir(parents=True)
            (self.path / "pid").write_text(str(os.getpid()))
            self._held = True

    def _is_stale(self) -> bool:
        try:
            pid = int((self.path / "pid").read_text().strip())
            os.kill(pid, 0)
            return False
        except (OSError, ValueError):
            return True

    def release(self) -> None:
        if self._held:
            shutil.rmtree(self.path, ignore_errors=True)
            self._held = False

    def __enter__(self) -> "GarminSyncLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()
