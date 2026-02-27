"""Shared distance and pace formatting helpers for API responses."""

KM_TO_MI = 0.621371192237334
KM_TO_YD = 1093.6132983377079
M_TO_MI = 0.0006213711922373339
M_TO_YD = 1.0936132983377078


def is_swim_discipline(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip().lower()
    return (
        "swim" in normalized
        or "pool" in normalized
        or "wetsuit" in normalized
    )


def format_distance_from_meters(
    meters: float | None, discipline: str | None = None
) -> str:
    if meters is None or meters <= 0:
        return "-"
    if is_swim_discipline(discipline):
        return f"{round(meters * M_TO_YD):,} yd"
    return f"{meters * M_TO_MI:.1f} mi"


def format_distance_from_kilometers(
    kilometers: float | None, discipline: str | None = None
) -> str:
    if kilometers is None or kilometers <= 0:
        return "-"
    if is_swim_discipline(discipline):
        return f"{round(kilometers * KM_TO_YD):,} yd"
    return f"{kilometers * KM_TO_MI:.1f} mi"


def format_pace_per_mile(seconds_per_km: float | None) -> str:
    if seconds_per_km is None or seconds_per_km <= 0:
        return "-"
    seconds_per_mile = int(round(seconds_per_km * 1.60934))
    minutes, seconds = divmod(seconds_per_mile, 60)
    return f"{minutes}:{seconds:02d}/mi"
