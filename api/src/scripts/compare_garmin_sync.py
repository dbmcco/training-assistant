#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


def _normalise(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalise(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return sorted((_normalise(item) for item in value), key=repr)
    return value


def _duplicate_ids(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        identifier = str(value)
        if identifier in seen:
            duplicates.add(identifier)
        seen.add(identifier)
    return sorted(duplicates)


def compare_reports(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    for field in ("status", "domains", "counts", "created_ids", "updated_ids", "deleted_ids", "skipped", "failures"):
        if _normalise(expected.get(field)) != _normalise(actual.get(field)):
            differences.append({"field": field, "expected": expected.get(field), "actual": actual.get(field)})

    actual_ids = list(actual.get("created_ids", [])) + list(actual.get("updated_ids", []))
    return {
        "status": "match" if not differences else "different",
        "differences": differences,
        "duplicate_candidates": _duplicate_ids(actual_ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two Garmin worker reports")
    parser.add_argument("expected", type=Path)
    parser.add_argument("actual", type=Path)
    args = parser.parse_args()
    report = compare_reports(json.loads(args.expected.read_text()), json.loads(args.actual.read_text()))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "match" and not report["duplicate_candidates"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
