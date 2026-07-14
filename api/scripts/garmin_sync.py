#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.integrations.garmin.config import GarminIntegrationSettings
from src.integrations.garmin.worker import GarminWorker, GarminWorkerArgs


def parse_args() -> GarminWorkerArgs:
    parser = argparse.ArgumentParser(description="Run the Training Assistant Garmin worker")
    parser.add_argument("--days-back", type=int, default=2)
    parser.add_argument("--activities-only", action="store_true")
    parser.add_argument("--daily-only", action="store_true")
    parser.add_argument("--calendar-only", action="store_true")
    parser.add_argument("--comprehensive", action="store_true")
    parser.add_argument("--calendar", action="store_true")
    parser.add_argument("--peloton", action="store_true")
    args = parser.parse_args()
    return GarminWorkerArgs(
        days_back=args.days_back,
        activities_only=args.activities_only,
        daily_only=args.daily_only,
        calendar_only=args.calendar_only,
        comprehensive=args.comprehensive,
        calendar=args.calendar,
        peloton=args.peloton,
    )


def main() -> int:
    report = GarminWorker(GarminIntegrationSettings.from_app_settings()).run(parse_args())
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] in {"success", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())
