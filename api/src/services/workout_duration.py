"""Utilities for planned workout duration normalization/formatting.

Garmin planned workouts are often stored in seconds, while manual edits may
store minutes. We normalize to minutes for display and to seconds for
comparisons.
"""


def normalize_planned_duration_minutes(raw_duration: int | float | None) -> int | None:
    """Return planned duration in minutes, handling seconds-vs-minutes inputs."""
    if raw_duration is None:
        return None

    value = float(raw_duration)
    if value <= 0:
        return None

    # Heuristic aligned with frontend behavior:
    # values >= 600 are likely seconds from Garmin plan payloads.
    if value >= 600:
        return int(round(value / 60.0))

    return int(round(value))


def planned_duration_seconds(raw_duration: int | float | None) -> float | None:
    """Return planned duration in seconds after normalization."""
    minutes = normalize_planned_duration_minutes(raw_duration)
    if minutes is None:
        return None
    return float(minutes * 60)


def format_planned_duration(raw_duration: int | float | None) -> str:
    """Human-readable planned duration string (e.g., '55m', '1h 7m')."""
    minutes = normalize_planned_duration_minutes(raw_duration)
    if minutes is None:
        return "-"
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remainder = minutes % 60
    return f"{hours}h {remainder}m" if remainder else f"{hours}h"
