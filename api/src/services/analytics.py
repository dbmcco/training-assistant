"""Analytics service for training load, volume, and trends."""

from datetime import date, datetime, timedelta, timezone
from statistics import pstdev
from typing import Any

from sqlalchemy import select, func, and_, case, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import GarminActivity, GarminDailySummary, Race


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


def _format_duration_from_seconds(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "0m"
    minutes = int(round(seconds / 60.0))
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remainder = minutes % 60
    return f"{hours}h {remainder}m" if remainder else f"{hours}h"


def _format_metric_value(value: float | None, unit: str) -> str:
    if value is None:
        return "--"
    numeric = float(value)
    if numeric.is_integer():
        core = str(int(numeric))
    else:
        core = f"{numeric:.1f}"
    if unit in {"", "score", "load"}:
        return core
    return f"{core} {unit}"


def _insight_severity(level: str) -> int:
    return {"warning": 3, "watch": 2, "good": 1}.get(level, 0)


async def trend_events(
    session: AsyncSession,
    start: date,
    end: date,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Return contextual events for trend chart annotation."""
    bounded_limit = max(1, min(limit, 30))
    events: list[dict[str, Any]] = []

    # Race events.
    race_result = await session.execute(
        select(Race)
        .where(and_(Race.date >= start, Race.date <= end))
        .order_by(Race.date.asc())
        .limit(8)
    )
    for race in race_result.scalars().all():
        events.append(
            {
                "date": race.date.isoformat(),
                "type": "race",
                "title": race.name,
                "detail": f"{race.distance_type} race day",
                "level": "good",
            }
        )

    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)

    # Long sessions (>= 90 minutes) to explain spikes in trend lines.
    long_result = await session.execute(
        select(
            func.date(GarminActivity.start_time).label("activity_day"),
            GarminActivity.activity_type,
            GarminActivity.duration_seconds,
            GarminActivity.name,
        )
        .where(
            and_(
                GarminActivity.start_time >= start_dt,
                GarminActivity.start_time < end_dt,
                GarminActivity.duration_seconds >= 5400,
            )
        )
        .order_by(GarminActivity.start_time.desc())
        .limit(30)
    )

    seen_long_keys: set[tuple[date, str]] = set()
    for row in long_result:
        if row.activity_day is None:
            continue
        activity_day = row.activity_day
        if isinstance(activity_day, datetime):
            activity_day = activity_day.date()
        discipline = _classify_discipline(row.activity_type)
        key = (activity_day, discipline)
        if key in seen_long_keys:
            continue
        seen_long_keys.add(key)
        session_name = row.name or row.activity_type or "session"
        events.append(
            {
                "date": activity_day.isoformat(),
                "type": "session",
                "title": f"Long {discipline}",
                "detail": f"{session_name} ({_format_duration_from_seconds(row.duration_seconds)})",
                "level": "watch" if (row.duration_seconds or 0) >= 7200 else "good",
            }
        )
        if len(seen_long_keys) >= 6:
            break

    # Recovery dips.
    recovery_result = await session.execute(
        select(
            GarminDailySummary.calendar_date,
            GarminDailySummary.training_readiness_score,
            GarminDailySummary.sleep_score,
        )
        .where(
            and_(
                GarminDailySummary.calendar_date >= start,
                GarminDailySummary.calendar_date <= end,
                or_(
                    GarminDailySummary.training_readiness_score < 40,
                    GarminDailySummary.sleep_score < 55,
                ),
            )
        )
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(8)
    )

    seen_recovery_dates: set[date] = set()
    for row in recovery_result:
        if row.calendar_date in seen_recovery_dates:
            continue
        seen_recovery_dates.add(row.calendar_date)
        parts: list[str] = []
        if row.training_readiness_score is not None:
            parts.append(f"readiness {int(row.training_readiness_score)}")
        if row.sleep_score is not None:
            parts.append(f"sleep {int(row.sleep_score)}")
        detail = ", ".join(parts) if parts else "low recovery signal"
        events.append(
            {
                "date": row.calendar_date.isoformat(),
                "type": "recovery",
                "title": "Recovery dip",
                "detail": detail,
                "level": "warning",
            }
        )

    deduped: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for event in sorted(events, key=lambda item: item["date"]):
        key = (event["date"], event["type"], event["title"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(event)

    return deduped[:bounded_limit]


def build_trend_coach_summary(
    metric_data: dict[str, Any],
    analysis: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create concise AI-style summary text for analysis page."""
    metric_label = metric_data.get("label", "Metric")
    unit = metric_data.get("unit", "")
    summary = metric_data.get("summary", {}) or {}
    latest = summary.get("latest")
    delta = summary.get("delta")

    if delta is None:
        trend_direction = "stable"
    elif delta > 0:
        trend_direction = "trending up"
    elif delta < 0:
        trend_direction = "trending down"
    else:
        trend_direction = "flat"

    headline = (
        f"{metric_label} is {trend_direction} "
        f"({ _format_metric_value(latest, unit) }) over this window."
    )

    insights = list(analysis.get("insights", []))
    top_insight = None
    if insights:
        top_insight = sorted(
            insights,
            key=lambda item: _insight_severity(str(item.get("level", ""))),
            reverse=True,
        )[0]

    load_management = analysis.get("load_management", {}) or {}
    acwr = load_management.get("acwr")
    acwr_band = load_management.get("acwr_band")
    consistency = analysis.get("consistency", {}) or {}
    consistency_pct = consistency.get("consistency_pct")

    bullets: list[str] = []
    if acwr is not None and acwr_band:
        bullets.append(f"Load context: ACWR {acwr} ({acwr_band.replace('_', ' ')}).")
    if consistency_pct is not None:
        bullets.append(f"Consistency: {consistency_pct}% active training days in this range.")
    if top_insight:
        bullets.append(f"Key signal: {top_insight.get('title')} — {top_insight.get('detail')}")

    if events:
        recent_event = events[-1]
        bullets.append(
            f"Recent event: {recent_event.get('date')} {recent_event.get('title')} "
            f"({recent_event.get('detail')})."
        )

    if top_insight and top_insight.get("level") == "warning":
        recommended_action = "Back off intensity for 24-48h and re-check readiness/sleep before the next hard session."
    elif acwr_band == "underloaded":
        recommended_action = "Add one quality session this week to rebuild momentum while keeping recovery stable."
    else:
        recommended_action = "Stay consistent with the current structure and adjust only if recovery trends dip."

    return {
        "headline": headline,
        "bullets": bullets[:3],
        "recommended_action": recommended_action,
    }


def build_daily_executive_summary(
    as_of: date,
    latest_summary: GarminDailySummary | None,
    analysis: dict[str, Any],
    plan_week: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a daily executive status and recommendations block."""
    readiness_score = (
        int(latest_summary.training_readiness_score)
        if latest_summary and latest_summary.training_readiness_score is not None
        else None
    )
    sleep_score = (
        int(latest_summary.sleep_score)
        if latest_summary and latest_summary.sleep_score is not None
        else None
    )
    body_battery = (
        int(latest_summary.body_battery_at_wake)
        if latest_summary and latest_summary.body_battery_at_wake is not None
        else None
    )

    load_management = analysis.get("load_management", {}) or {}
    acwr = load_management.get("acwr")
    acwr_band = load_management.get("acwr_band")

    recovery_trend = analysis.get("recovery_trend", {}) or {}
    readiness_delta = recovery_trend.get("readiness_delta")
    sleep_delta = recovery_trend.get("sleep_delta")

    level: str = "good"
    if (readiness_score is not None and readiness_score < 45) or acwr_band == "overreaching_risk":
        level = "warning"
    elif (
        (readiness_score is not None and readiness_score < 65)
        or acwr_band == "underloaded"
        or (readiness_delta is not None and readiness_delta <= -8)
        or (sleep_delta is not None and sleep_delta <= -5)
    ):
        level = "watch"

    status_title_by_level = {
        "good": "On Track",
        "watch": "Monitor & Adjust",
        "warning": "Recovery Priority",
    }

    summary_parts: list[str] = []
    if readiness_score is not None:
        summary_parts.append(f"Readiness {readiness_score}")
    if sleep_score is not None:
        summary_parts.append(f"Sleep {sleep_score}")
    if body_battery is not None:
        summary_parts.append(f"Body battery {body_battery}")
    if acwr is not None:
        band_text = f" ({str(acwr_band).replace('_', ' ')})" if acwr_band else ""
        summary_parts.append(f"ACWR {acwr}{band_text}")

    consistency_pct = analysis.get("consistency", {}).get("consistency_pct")
    if consistency_pct is not None:
        summary_parts.append(f"Consistency {consistency_pct}%")
    if plan_week and plan_week.get("total_planned", 0) > 0:
        summary_parts.append(
            "Plan "
            f"{plan_week.get('on_plan_completed', 0)}/{plan_week.get('total_planned', 0)} on plan"
        )

    summary_line = (
        " | ".join(summary_parts)
        if summary_parts
        else "No complete daily summary data yet; using trend history where available."
    )

    recommendations: list[str] = []
    if level == "warning":
        recommendations.append(
            "Prioritize recovery today: easy aerobic only or full rest before the next quality session."
        )
    if acwr_band == "overreaching_risk":
        recommendations.append(
            "Reduce volume/intensity for 24-48h and re-check readiness + sleep before resuming hard work."
        )
    elif acwr_band == "underloaded":
        recommendations.append(
            "Add one targeted quality session this week to rebuild load progressively."
        )

    discipline_balance = analysis.get("discipline_balance", {}) or {}
    swim_pct = (discipline_balance.get("swim") or {}).get("pct")
    if swim_pct is not None and swim_pct < 15:
        recommendations.append(
            "Rebalance toward race specificity by adding at least one swim-focused session."
        )

    if consistency_pct is not None and consistency_pct < 60:
        recommendations.append(
            "Protect consistency with shorter sessions on busy days to keep momentum."
        )

    insights = list(analysis.get("insights", []))
    if insights:
        top = sorted(
            insights,
            key=lambda item: _insight_severity(str(item.get("level", ""))),
            reverse=True,
        )[0]
        top_title = str(top.get("title") or "").strip()
        top_detail = str(top.get("detail") or "").strip()
        if top_title and top_detail:
            recommendations.append(f"{top_title}: {top_detail}")

    deduped_recommendations: list[str] = []
    for rec in recommendations:
        if rec not in deduped_recommendations:
            deduped_recommendations.append(rec)

    if not deduped_recommendations:
        deduped_recommendations = [
            "Stay consistent with the current structure and keep easy days truly easy."
        ]

    if plan_week:
        remaining = int(plan_week.get("remaining", 0) or 0)
        next_sessions = list(plan_week.get("next_sessions", []))
        if remaining > 0:
            deduped_recommendations.insert(
                0, f"Execute your remaining {remaining} planned session(s) this week."
            )
        if next_sessions:
            next_session = next_sessions[0]
            next_date = next_session.get("date", "upcoming")
            next_label = next_session.get("label", "planned session")
            deduped_recommendations.insert(
                1, f"Next key session: {next_date} {next_label}."
            )

    ordered_recommendations: list[str] = []
    for rec in deduped_recommendations:
        if rec not in ordered_recommendations:
            ordered_recommendations.append(rec)

    return {
        "as_of": as_of.isoformat(),
        "status_level": level,
        "status": status_title_by_level.get(level, "Monitor"),
        "summary": summary_line,
        "recommendations": ordered_recommendations[:3],
    }


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
