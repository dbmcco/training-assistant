"""Recovery-time normalization helpers.

Garmin payloads expose training readiness `recoveryTime` values that are
minute-scale. Our DB column is named `recovery_time_hours`, so this helper
normalizes stored values into true hours for scoring and messaging.
"""

from __future__ import annotations

from typing import Any


def normalize_recovery_time_hours(
    stored_value: int | float | None,
    raw_data: dict[str, Any] | None = None,
) -> float | None:
    """Return recovery time in hours from stored Garmin daily summary value."""
    if stored_value is None:
        return None

    value = float(stored_value)
    if value < 0:
        return None

    if _raw_payload_confirms_minutes(value, raw_data):
        return round(value / 60.0, 1)

    # Guardrail for impossible "hours" values in case raw_data is missing.
    if value > 96:
        return round(value / 60.0, 1)

    return value


def _raw_payload_confirms_minutes(
    value: float,
    raw_data: dict[str, Any] | None,
) -> bool:
    if not isinstance(raw_data, dict):
        return False

    training_readiness = raw_data.get("training_readiness")
    if isinstance(training_readiness, list):
        for item in training_readiness:
            if not isinstance(item, dict):
                continue
            recovery_time = item.get("recoveryTime")
            if isinstance(recovery_time, (int, float)) and float(recovery_time) == value:
                return True

    morning_readiness = raw_data.get("morning_readiness")
    if isinstance(morning_readiness, dict):
        recovery_time = morning_readiness.get("recoveryTime")
        if isinstance(recovery_time, (int, float)) and float(recovery_time) == value:
            return True

    return False
