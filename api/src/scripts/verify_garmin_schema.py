#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2

from src.config import settings

REQUIRED_COLUMNS = {
    "garmin_activities": {"id", "garmin_activity_id", "start_time", "raw_data"},
    "garmin_daily_summary": {"id", "calendar_date", "training_readiness_score", "raw_data"},
    "athlete_biometrics": {"id", "date", "raw_data"},
}


def verify_garmin_schema(database_url: str | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "success",
        "tables": {},
        "row_counts": {},
        "missing_tables": [],
        "missing_columns": {},
        "identifier_counts": {},
    }
    conn = psycopg2.connect(database_url or settings.database_url_sync)
    try:
        with conn.cursor() as cur:
            for table, columns in REQUIRED_COLUMNS.items():
                cur.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = %s)",
                    (table,),
                )
                exists = bool(cur.fetchone()[0])
                report["tables"][table] = exists
                if not exists:
                    report["missing_tables"].append(table)
                    continue

                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table,),
                )
                actual_columns = {row[0] for row in cur.fetchall()}
                missing = sorted(columns - actual_columns)
                if missing:
                    report["missing_columns"][table] = missing
                cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                report["row_counts"][table] = int(cur.fetchone()[0])

            if report["tables"].get("garmin_activities"):
                cur.execute("SELECT COUNT(DISTINCT garmin_activity_id) FROM garmin_activities")
                report["identifier_counts"]["garmin_activity_id"] = int(cur.fetchone()[0])
            if report["tables"].get("garmin_daily_summary"):
                cur.execute("SELECT COUNT(DISTINCT calendar_date) FROM garmin_daily_summary")
                report["identifier_counts"]["calendar_date"] = int(cur.fetchone()[0])
            if report["tables"].get("athlete_biometrics"):
                cur.execute("SELECT COUNT(DISTINCT date) FROM athlete_biometrics")
                report["identifier_counts"]["biometric_date"] = int(cur.fetchone()[0])
    finally:
        conn.close()

    if report["missing_tables"] or report["missing_columns"]:
        report["status"] = "failed"
    return report


def main() -> int:
    report = verify_garmin_schema()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
