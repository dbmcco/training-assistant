"""Analytics service for training load, volume, and trends."""

from datetime import date, datetime, timedelta, timezone
from statistics import pstdev
from typing import Any

from sqlalchemy import select, func, and_, case, or_
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

METRIC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "readiness": {
        "column": GarminDailySummary.training_readiness_score,
        "label": "Readiness",
        "unit": "score",
    },
    "hrv_7d": {
        "column": GarminDailySummary.hrv_7d_avg,
        "label": "HRV (7d avg)",
        "unit": "ms",
    },
    "hrv_night": {
        "column": GarminDailySummary.hrv_last_night,
        "label": "HRV (last night)",
        "unit": "ms",
    },
    "sleep_score": {
        "column": GarminDailySummary.sleep_score,
        "label": "Sleep score",
        "unit": "score",
    },
    "body_battery": {
        "column": GarminDailySummary.body_battery_at_wake,
        "label": "Body battery at wake",
        "unit": "score",
    },
    "resting_hr": {
        "column": GarminDailySummary.resting_heart_rate,
        "label": "Resting HR",
        "unit": "bpm",
    },
    "load_7d": {
        "column": GarminDailySummary.training_load_7d,
        "label": "Training load (7d)",
        "unit": "load",
    },
    "load_28d": {
        "column": GarminDailySummary.training_load_28d,
        "label": "Training load (28d)",
        "unit": "load",
    },
    "vo2_run": {
        "column": GarminDailySummary.vo2_max_run,
        "label": "VO2 max run",
        "unit": "ml/kg/min",
    },
    "vo2_bike": {
        "column": GarminDailySummary.vo2_max_cycling,
        "label": "VO2 max bike",
        "unit": "ml/kg/min",
    },
    "endurance": {
        "column": GarminDailySummary.endurance_score,
        "label": "Endurance score",
        "unit": "score",
    },
    "stress": {
        "column": GarminDailySummary.average_stress,
        "label": "Average stress",
        "unit": "score",
    },
}


def _classify_discipline(activity_type: str | None) -> str:
    if not activity_type:
        return "other"
    return DISCIPLINE_MAP.get(activity_type, "other")


def trend_metric_options() -> list[dict[str, str]]:
    """List available metric keys and labels for trend charts."""
    return [
        {"key": key, "label": cfg["label"], "unit": cfg["unit"]}
        for key, cfg in METRIC_DEFINITIONS.items()
    ]


async def trend_data_window(session: AsyncSession) -> dict[str, date | None]:
    """Return earliest/latest dates across trend-capable Garmin data."""
    daily_bounds = await session.execute(
        select(
            func.min(GarminDailySummary.calendar_date).label("min_date"),
            func.max(GarminDailySummary.calendar_date).label("max_date"),
        )
    )
    daily_row = daily_bounds.one()

    activity_bounds = await session.execute(
        select(
            func.min(func.date(GarminActivity.start_time)).label("min_date"),
            func.max(func.date(GarminActivity.start_time)).label("max_date"),
        )
    )
    activity_row = activity_bounds.one()

    min_candidates = [d for d in (daily_row.min_date, activity_row.min_date) if d is not None]
    max_candidates = [d for d in (daily_row.max_date, activity_row.max_date) if d is not None]

    return {
        "earliest_date": min(min_candidates) if min_candidates else None,
        "latest_date": max(max_candidates) if max_candidates else None,
    }


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


async def activity_type_breakdown(
    session: AsyncSession,
    start: date,
    end: date,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return activity-type totals ordered by most frequent."""
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)

    result = await session.execute(
        select(
            GarminActivity.activity_type,
            func.count().label("count"),
            func.sum(GarminActivity.duration_seconds).label("total_seconds"),
            func.sum(GarminActivity.distance_meters).label("total_meters"),
        )
        .where(
            and_(
                GarminActivity.start_time >= start_dt,
                GarminActivity.start_time < end_dt,
            )
        )
        .group_by(GarminActivity.activity_type)
        .order_by(func.count().desc(), GarminActivity.activity_type.asc())
        .limit(limit)
    )

    rows = []
    for row in result:
        rows.append(
            {
                "activity_type": row.activity_type or "unknown",
                "count": int(row.count or 0),
                "hours": round((row.total_seconds or 0) / 3600.0, 1),
                "distance_km": round((row.total_meters or 0) / 1000.0, 1),
                "discipline": _classify_discipline(row.activity_type),
            }
        )
    return rows


async def daily_metric_trend(
    session: AsyncSession,
    start: date,
    end: date,
    metric: str,
) -> dict[str, Any]:
    """Return a single daily metric timeseries and summary statistics."""
    metric_key = metric if metric in METRIC_DEFINITIONS else "readiness"
    cfg = METRIC_DEFINITIONS[metric_key]
    col = cfg["column"]

    result = await session.execute(
        select(
            GarminDailySummary.calendar_date,
            col.label("value"),
        )
        .where(
            and_(
                GarminDailySummary.calendar_date >= start,
                GarminDailySummary.calendar_date <= end,
            )
        )
        .order_by(GarminDailySummary.calendar_date.asc())
    )

    series = []
    values: list[float] = []
    for row in result:
        value = row.value
        if value is not None:
            values.append(float(value))
        series.append(
            {
                "date": row.calendar_date.isoformat(),
                "value": float(value) if value is not None else None,
            }
        )

    summary: dict[str, Any] = {
        "count": len(values),
        "latest": values[-1] if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "avg": round(sum(values) / len(values), 2) if values else None,
        "delta": round(values[-1] - values[0], 2) if len(values) >= 2 else None,
    }

    return {
        "metric": metric_key,
        "label": cfg["label"],
        "unit": cfg["unit"],
        "series": series,
        "summary": summary,
    }


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _window_delta(values: list[float | None]) -> float | None:
    recent = [float(v) for v in values[-7:] if v is not None]
    previous = [float(v) for v in values[-14:-7] if v is not None]
    if not recent or not previous:
        return None
    return round((_avg(recent) or 0.0) - (_avg(previous) or 0.0), 2)


async def coaching_analysis(
    session: AsyncSession,
    start: date,
    end: date,
    volume: dict[str, dict[str, float]],
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Return coaching-oriented analysis and heuristic insights."""
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)

    # Daily activity hours across the full range (rest days included as zero).
    day_result = await session.execute(
        select(
            func.date(GarminActivity.start_time).label("activity_day"),
            func.sum(GarminActivity.duration_seconds).label("total_seconds"),
        )
        .where(
            and_(
                GarminActivity.start_time >= start_dt,
                GarminActivity.start_time < end_dt,
            )
        )
        .group_by(func.date(GarminActivity.start_time))
        .order_by(func.date(GarminActivity.start_time).asc())
    )
    daily_seconds: dict[date, float] = {}
    for row in day_result:
        if row.activity_day is None:
            continue
        activity_day = row.activity_day
        if isinstance(activity_day, datetime):
            activity_day = activity_day.date()
        daily_seconds[activity_day] = float(row.total_seconds or 0.0)

    period_days = max((end - start).days + 1, 1)
    daily_hours: list[float] = []
    active_days = 0
    for offset in range(period_days):
        day = start + timedelta(days=offset)
        hours = daily_seconds.get(day, 0.0) / 3600.0
        daily_hours.append(hours)
        if hours > 0:
            active_days += 1

    total_hours = float(sum(daily_hours))
    avg_daily_hours = total_hours / period_days
    day_stddev = pstdev(daily_hours) if len(daily_hours) >= 2 else 0.0
    monotony = round(avg_daily_hours / day_stddev, 2) if day_stddev > 0 else None
    strain = round(total_hours * monotony, 1) if monotony is not None else None
    consistency_pct = round((active_days / period_days) * 100.0, 1)

    recent_week_hours = round(sum(daily_hours[-7:]), 1) if daily_hours else 0.0
    previous_week_slice = daily_hours[-14:-7]
    previous_week_hours = round(sum(previous_week_slice), 1) if previous_week_slice else None
    ramp_hours = (
        round(recent_week_hours - previous_week_hours, 1)
        if previous_week_hours is not None
        else None
    )
    ramp_pct = (
        round((ramp_hours / previous_week_hours) * 100.0, 1)
        if ramp_hours is not None and previous_week_hours and previous_week_hours > 0
        else None
    )

    # Session profile (hard/long sessions and average duration).
    session_profile_result = await session.execute(
        select(
            func.count().label("session_count"),
            func.sum(
                case(
                    (
                        or_(
                            GarminActivity.aerobic_training_effect >= 3.0,
                            GarminActivity.anaerobic_training_effect >= 1.0,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("hard_sessions"),
            func.sum(
                case(
                    (GarminActivity.duration_seconds >= 5400, 1),
                    else_=0,
                )
            ).label("long_sessions"),
            func.avg(GarminActivity.duration_seconds).label("avg_duration_seconds"),
            func.max(GarminActivity.duration_seconds).label("max_duration_seconds"),
        )
        .where(
            and_(
                GarminActivity.start_time >= start_dt,
                GarminActivity.start_time < end_dt,
            )
        )
    )
    session_row = session_profile_result.one()
    session_count = int(session_row.session_count or 0)
    hard_sessions = int(session_row.hard_sessions or 0)
    hard_pct = round((hard_sessions / session_count) * 100.0, 1) if session_count > 0 else None

    # Recovery/load trends from daily summaries.
    summary_result = await session.execute(
        select(
            GarminDailySummary.calendar_date,
            GarminDailySummary.training_load_7d,
            GarminDailySummary.training_load_28d,
            GarminDailySummary.training_readiness_score,
            GarminDailySummary.sleep_score,
            GarminDailySummary.hrv_7d_avg,
            GarminDailySummary.resting_heart_rate,
        )
        .where(
            and_(
                GarminDailySummary.calendar_date >= start,
                GarminDailySummary.calendar_date <= end,
            )
        )
        .order_by(GarminDailySummary.calendar_date.asc())
    )
    summary_rows = list(summary_result)

    readiness_values = [row.training_readiness_score for row in summary_rows]
    sleep_values = [row.sleep_score for row in summary_rows]
    hrv_values = [row.hrv_7d_avg for row in summary_rows]
    rhr_values = [row.resting_heart_rate for row in summary_rows]

    acwr = None
    latest_load_7d = None
    latest_load_28d = None
    for row in reversed(summary_rows):
        load_7d = row.training_load_7d
        load_28d = row.training_load_28d
        if load_7d is None or load_28d is None or load_28d <= 0:
            continue
        latest_load_7d = float(load_7d)
        latest_load_28d = float(load_28d)
        acwr = round(latest_load_7d / latest_load_28d, 2)
        break

    acwr_band = None
    if acwr is not None:
        if acwr < 0.8:
            acwr_band = "underloaded"
        elif acwr <= 1.3:
            acwr_band = "balanced"
        else:
            acwr_band = "overreaching_risk"

    tri_hours = {
        "run": round(float(volume.get("run", {}).get("hours", 0.0)), 1),
        "bike": round(float(volume.get("bike", {}).get("hours", 0.0)), 1),
        "swim": round(float(volume.get("swim", {}).get("hours", 0.0)), 1),
    }
    tri_total = sum(tri_hours.values())
    discipline_balance = {
        key: {
            "hours": hours,
            "pct": round((hours / tri_total) * 100.0, 1) if tri_total > 0 else 0.0,
        }
        for key, hours in tri_hours.items()
    }

    recovery_trend = {
        "readiness_delta": _window_delta(readiness_values),
        "sleep_delta": _window_delta(sleep_values),
        "hrv_delta": _window_delta(hrv_values),
        # For RHR, positive is usually worse; retain raw delta and derive direction in UI.
        "rhr_delta": _window_delta(rhr_values),
    }

    insights: list[dict[str, str]] = []
    if acwr is not None and acwr > 1.3:
        insights.append(
            {
                "level": "warning",
                "title": "Acute load is elevated",
                "detail": f"ACWR is {acwr}, above the typical 0.8-1.3 range. Consider a lighter block.",
            }
        )
    elif acwr is not None and acwr < 0.8:
        insights.append(
            {
                "level": "watch",
                "title": "Load may be too low",
                "detail": f"ACWR is {acwr}. You may be underloading if race specificity is a priority.",
            }
        )
    elif acwr is not None:
        insights.append(
            {
                "level": "good",
                "title": "Load balance looks stable",
                "detail": f"ACWR is {acwr} and currently in a balanced range.",
            }
        )

    if consistency_pct < 55:
        insights.append(
            {
                "level": "warning",
                "title": "Consistency is low",
                "detail": f"Active training days are {consistency_pct}% of this window.",
            }
        )
    elif consistency_pct >= 75:
        insights.append(
            {
                "level": "good",
                "title": "Consistency is strong",
                "detail": f"Active training days are {consistency_pct}% of this window.",
            }
        )

    readiness_delta = recovery_trend["readiness_delta"]
    sleep_delta = recovery_trend["sleep_delta"]
    if (readiness_delta is not None and readiness_delta <= -8) or (
        sleep_delta is not None and sleep_delta <= -5
    ):
        insights.append(
            {
                "level": "warning",
                "title": "Recovery trend is dropping",
                "detail": "Readiness and/or sleep has declined versus the previous week.",
            }
        )

    if hard_pct is not None and hard_pct > 40:
        insights.append(
            {
                "level": "watch",
                "title": "High intensity density",
                "detail": f"{hard_pct}% of sessions are marked hard in this window.",
            }
        )

    if tri_total > 0 and tri_hours["swim"] == 0:
        insights.append(
            {
                "level": "watch",
                "title": "Swim volume is missing",
                "detail": "No swim hours were detected in the current analysis window.",
            }
        )

    return {
        "consistency": {
            "active_days": active_days,
            "period_days": period_days,
            "consistency_pct": consistency_pct,
            "avg_daily_hours": round(avg_daily_hours, 2),
            "monotony": monotony,
            "strain": strain,
        },
        "load_management": {
            "recent_week_hours": recent_week_hours,
            "previous_week_hours": previous_week_hours,
            "ramp_hours": ramp_hours,
            "ramp_pct": ramp_pct,
            "acwr": acwr,
            "acwr_band": acwr_band,
            "latest_load_7d": round(latest_load_7d, 1) if latest_load_7d is not None else None,
            "latest_load_28d": round(latest_load_28d, 1) if latest_load_28d is not None else None,
        },
        "recovery_trend": recovery_trend,
        "session_profile": {
            "session_count": session_count,
            "hard_sessions": hard_sessions,
            "hard_pct": hard_pct,
            "long_sessions": int(session_row.long_sessions or 0),
            "avg_session_duration_min": round((session_row.avg_duration_seconds or 0) / 60.0, 1)
            if session_row.avg_duration_seconds
            else None,
            "longest_session_min": round((session_row.max_duration_seconds or 0) / 60.0, 1)
            if session_row.max_duration_seconds
            else None,
        },
        "discipline_balance": discipline_balance,
        "insights": insights,
        "totals": {
            "total_hours": round(total_hours, 1),
            "total_activities": int(stats.get("total_activities", 0)),
        },
    }
