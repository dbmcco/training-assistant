from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import Settings, settings


@dataclass(frozen=True)
class GarminIntegrationSettings:
    enabled: bool
    tokenstore_path: Path
    lock_path: Path
    days_back: int
    calendar_months_ahead: int
    timeout_seconds: int
    plan_ownership_mode: str
    peloton_enabled: bool
    peloton_email: str
    peloton_password: str

    @classmethod
    def from_app_settings(
        cls, app_settings: Settings = settings
    ) -> "GarminIntegrationSettings":
        return cls(
            enabled=app_settings.garmin_integration_enabled,
            tokenstore_path=Path(app_settings.garmin_tokenstore_path).expanduser(),
            lock_path=Path(app_settings.garmin_sync_lock_path).expanduser(),
            days_back=max(app_settings.garmin_sync_days_back, 0),
            calendar_months_ahead=max(app_settings.garmin_calendar_months_ahead, 0),
            timeout_seconds=max(app_settings.garmin_sync_timeout_seconds, 5),
            plan_ownership_mode=app_settings.plan_ownership_mode.strip().lower(),
            peloton_enabled=app_settings.peloton_enabled,
            peloton_email=app_settings.peloton_email,
            peloton_password=app_settings.peloton_password,
        )


__all__ = ["GarminIntegrationSettings"]
