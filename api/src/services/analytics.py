"""Analytics service for training load, volume, and trends."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import GarminActivity, GarminDailySummary


# Map Garmin activity_type values to triathlon disciplines
DISCIPLINE_MAP = {
    "running": "run",
    "trail_running": "run",
    "treadmill_running": "run",
    "track_running": "run",
    "cycling": "bike",
    "indoor_cycling": "bike",
    "virtual_ride": "bike",
    "mountain_biking": "bike",
    "hiit": "cross_training",
    "indoor_cardio": "cross_training",
    "yoga": "cross_training",
    "pilates": "cross_training",
    "elliptical": "cross_training",
    "stair_climbing": "cross_training",
    "lap_swimming": "swim",
    "open_water_swimming": "swim",
    "pool_swimming": "swim",
    "strength_training": "strength",
    "walking": "walk",
    "hiking": "walk",
    "resort_skiing": "other",
}


def _classify_discipline(activity_type: str | None) -> str:
    if not activity_type:
        return "other"
    return DISCIPLINE_MAP.get(activity_type, "other")


async def weekly_volume_by_discipline(
    session: AsyncSession,
    start: date,
    end: date,
) -> dict[str, dict[str, float]]:
    """Aggregate training volume by discipline for a date range.

    Returns: {"run": {"hours": 3.5, "distance_km": 28.0}, "bike": {...}, ...}
    """
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)

    result = await session.execute(
        select(
            GarminActivity.activity_type,
            func.sum(GarminActivity.duration_seconds).label("total_seconds"),
            func.sum(GarminActivity.distance_meters).label("total_meters"),
            func.count().label("count"),
        )
        .where(
            and_(
                GarminActivity.start_time >= start_dt,
                GarminActivity.start_time < end_dt,
            )
        )
        .group_by(GarminActivity.activity_type)
    )

    volumes: dict[str, dict[str, float]] = {}
    for row in result:
        discipline = _classify_discipline(row.activity_type)
        if discipline not in volumes:
            volumes[discipline] = {"hours": 0.0, "distance_km": 0.0, "count": 0}
        volumes[discipline]["hours"] += (row.total_seconds or 0) / 3600.0
        volumes[discipline]["distance_km"] += (row.total_meters or 0) / 1000.0
        volumes[discipline]["count"] += row.count

    # Round for cleanliness
    for d in volumes.values():
        d["hours"] = round(d["hours"], 1)
        d["distance_km"] = round(d["distance_km"], 1)

    return volumes


async def training_load_trend(
    session: AsyncSession,
    weeks: int = 4,
) -> list[dict]:
    """Return weekly training load data from garmin_daily_summary.

    Returns list of {"week_start": date, "load_7d": float, "load_28d": float}
    """
    end = date.today()
    start = end - timedelta(weeks=weeks)

    result = await session.execute(
        select(
            GarminDailySummary.calendar_date,
            GarminDailySummary.training_load_7d,
            GarminDailySummary.training_load_28d,
        )
        .where(GarminDailySummary.calendar_date >= start)
        .order_by(GarminDailySummary.calendar_date)
    )

    # Group by ISO week
    weeks_data: dict[str, dict] = {}
    for row in result:
        week_start = row.calendar_date - timedelta(days=row.calendar_date.weekday())
        key = week_start.isoformat()
        # Take the latest value for each week
        weeks_data[key] = {
            "week_start": week_start.isoformat(),
            "load_7d": row.training_load_7d,
            "load_28d": row.training_load_28d,
        }

    return list(weeks_data.values())


async def activity_stats(
    session: AsyncSession,
    start: date,
    end: date,
) -> dict:
    """Aggregate activity statistics for a date range."""
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)

    result = await session.execute(
        select(
            func.count().label("total"),
            func.sum(GarminActivity.duration_seconds).label("total_seconds"),
            func.sum(GarminActivity.distance_meters).label("total_meters"),
            func.avg(GarminActivity.average_hr).label("avg_hr"),
        )
        .where(
            and_(
                GarminActivity.start_time >= start_dt,
                GarminActivity.start_time < end_dt,
            )
        )
    )

    row = result.one()
    return {
        "total_activities": row.total or 0,
        "total_hours": round((row.total_seconds or 0) / 3600.0, 1),
        "total_distance_km": round((row.total_meters or 0) / 1000.0, 1),
        "avg_hr": round(row.avg_hr, 0) if row.avg_hr else None,
    }
