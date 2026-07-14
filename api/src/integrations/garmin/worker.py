from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from src.integrations.garmin.config import GarminIntegrationSettings
from src.integrations.garmin.locks import GarminSyncLock
from src.integrations.garmin.peloton import GarminPelotonImporter
from src.integrations.garmin.report import SyncReport
from src.integrations.garmin.sync_engine import GarminSyncClient


@dataclass(frozen=True)
class GarminWorkerArgs:
    days_back: int = 2
    activities_only: bool = False
    daily_only: bool = False
    calendar_only: bool = False
    comprehensive: bool = False
    calendar: bool = False
    peloton: bool = False


class GarminWorker:
    def __init__(
        self,
        integration_settings: GarminIntegrationSettings,
        client_factory: Callable[..., GarminSyncClient] = GarminSyncClient,
    ) -> None:
        self.integration_settings = integration_settings
        self.client_factory = client_factory

    def run(self, args: GarminWorkerArgs) -> dict:
        report = SyncReport()
        if not self.integration_settings.enabled:
            report.status = "skipped"
            report.skipped.append({"reason": "garmin_integration_disabled"})
            return report.as_dict()

        try:
            lock = GarminSyncLock(self.integration_settings.lock_path)
            lock.acquire()
        except RuntimeError as exc:
            report.status = "skipped"
            report.skipped.append({"reason": "sync_already_running", "error": str(exc)})
            return report.as_dict()

        client: GarminSyncClient | None = None
        try:
            client = self.client_factory(self.integration_settings)
            days_back = max(args.days_back, 0)
            if args.calendar_only:
                client.ensure_schema()
                result = client.sync_calendar(
                    months_ahead=self.integration_settings.calendar_months_ahead
                )
                report.add_domain("calendar", result)
            elif args.activities_only:
                client.ensure_schema()
                report.add_domain("activities", {"updated": client.sync_activities(days_back)})
            elif args.daily_only:
                client.ensure_schema()
                end_date = date.today()
                start_date = end_date - timedelta(days=days_back)
                report.add_domain("daily_summary", {"updated": client.sync_daily_range(start_date, end_date)})
            else:
                result = client.full_sync(
                    days_back,
                    comprehensive=args.comprehensive,
                    include_calendar=args.calendar,
                )
                report.add_domain("sync", result)

            if args.peloton:
                report.add_domain(
                    "peloton",
                    GarminPelotonImporter(self.integration_settings).sync(days_back),
                )
            return report.as_dict()
        except Exception as exc:
            report.add_failure("worker", exc)
            return report.as_dict()
        finally:
            if client is not None:
                client.close()
            lock.release()
