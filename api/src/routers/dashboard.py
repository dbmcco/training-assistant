"""Dashboard API routes for the Training Assistant."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import DailyBriefing, GarminDailySummary, PlannedWorkout, Race
from src.services.analytics import (
    activity_stats,
    activity_type_breakdown,
    build_daily_executive_summary,
    build_trend_coach_summary,
    coaching_analysis,
    daily_metric_trend,
    trend_events,
    trend_data_window,
    trend_metric_options,
    training_load_trend,
    weekly_volume_by_discipline,
)
from src.services.plan_engine import (
    get_plan_adherence,
    get_today_workout,
)
from src.services.plan_changes import refresh_with_plan_change_tracking
from src.services.recovery_time import normalize_recovery_time_hours
from src.services.readiness import compute_readiness
from src.services.recommendations import (
    get_briefing_recommendation,
    serialize_recommendation,
)
from src.services.workout_duration import format_planned_duration

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _has_recovery_metrics(summary: GarminDailySummary | None) -> bool:
    if summary is None:
        return False
    return any(
        value is not None
        for value in (
            summary.sleep_score,
            summary.body_battery_at_wake,
            summary.hrv_last_night,
            summary.resting_heart_rate,
            summary.training_readiness_score,
        )
    )


async def _select_latest_dashboard_summary(
    db: AsyncSession,
) -> tuple[GarminDailySummary | None, GarminDailySummary | None]:
    latest_result = await db.execute(
        select(GarminDailySummary)
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    latest_summary = latest_result.scalar_one_or_none()

    if _has_recovery_metrics(latest_summary):
        return latest_summary, latest_summary

    fallback_result = await db.execute(
        select(GarminDailySummary)
        .where(
            or_(
                GarminDailySummary.sleep_score.is_not(None),
                GarminDailySummary.body_battery_at_wake.is_not(None),
                GarminDailySummary.hrv_last_night.is_not(None),
                GarminDailySummary.resting_heart_rate.is_not(None),
                GarminDailySummary.training_readiness_score.is_not(None),
            )
        )
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    summary_for_metrics = fallback_result.scalar_one_or_none() or latest_summary
    return latest_summary, summary_for_metrics


@router.post("/refresh")
async def dashboard_refresh(
    include_calendar: bool = Query(
        default=False,
        description="Also refresh planned workouts/calendar in addition to today's summary.",
    ),
    force: bool = Query(
        default=False,
        description="Bypass short refresh cooldown and run immediately.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Refresh Garmin data on demand (typically called on app refresh)."""
    result, events = await refresh_with_plan_change_tracking(
        db,
        include_calendar=include_calendar,
        force=force,
        source="dashboard_refresh",
    )
    if not events:
        return result

    return {
        **result,
        "plan_changes_detected": len(events),
        "plan_changes": events[:10],
    }


@router.get("/today")
async def dashboard_today(db: AsyncSession = Depends(get_db)):
    """Return today's dashboard snapshot: readiness, workout, races, briefing, metrics."""
    today = date.today()

    latest_summary, summary = await _select_latest_dashboard_summary(db)

    # Compute readiness from the latest summary with usable recovery metrics.
    if summary:
        recovery_time_hours = normalize_recovery_time_hours(
            summary.recovery_time_hours,
            summary.raw_data,
        )
        readiness = compute_readiness(
            hrv_last_night=summary.hrv_last_night,
            hrv_7d_avg=summary.hrv_7d_avg,
            sleep_score=summary.sleep_score,
            body_battery_wake=summary.body_battery_at_wake,
            recovery_time_hours=recovery_time_hours,
            training_load_7d=summary.training_load_7d,
            training_load_28d=summary.training_load_28d,
        )
        readiness_data = {
            "score": readiness.score,
            "label": readiness.label,
            "components": [
                {
                    "name": c.name,
                    "value": c.value,
                    "normalized": c.normalized,
                    "weight": c.weight,
                    "detail": c.detail,
                }
                for c in readiness.components
            ],
        }
        metrics = {
            "sleep_score": summary.sleep_score,
            "body_battery_wake": summary.body_battery_at_wake,
            "hrv_last_night": summary.hrv_last_night,
            "resting_hr": summary.resting_heart_rate,
        }
        training_status = (
            latest_summary.training_status
            if latest_summary and latest_summary.training_status is not None
            else summary.training_status
        )
    else:
        readiness_data = {"score": 50, "label": "Moderate", "components": []}
        metrics = {
            "sleep_score": None,
            "body_battery_wake": None,
            "hrv_last_night": None,
            "resting_hr": None,
        }
        training_status = None

    # Today's planned workout
    today_workout = await get_today_workout(db)

    # Upcoming races with weeks_out
    races_result = await db.execute(
        select(Race)
        .where(Race.date >= today)
        .order_by(Race.date)
    )
    races = []
    for race in races_result.scalars().all():
        weeks_out = (race.date - today).days // 7
        races.append({
            "id": str(race.id),
            "name": race.name,
            "date": race.date.isoformat(),
            "distance_type": race.distance_type,
            "goal_time": race.goal_time,
            "weeks_out": weeks_out,
        })

    # Today's briefing
    briefing_result = await db.execute(
        select(DailyBriefing).where(DailyBriefing.date == today)
    )
    briefing_row = briefing_result.scalar_one_or_none()
    briefing = None
    if briefing_row:
        recommendation_row = await get_briefing_recommendation(db, briefing_row.id)
        briefing = {
            "content": briefing_row.content,
            "readiness_summary": briefing_row.readiness_summary,
            "workout_recommendation": briefing_row.workout_recommendation,
            "alerts": briefing_row.alerts,
            "recommendation_change": serialize_recommendation(recommendation_row) if recommendation_row else None,
        }

    return {
        "date": today.isoformat(),
        "readiness": readiness_data,
        "today_workout": today_workout,
        "races": races,
        "briefing": briefing,
        "training_status": training_status,
        "metrics": metrics,
    }


@router.get("/weekly")
async def dashboard_weekly(db: AsyncSession = Depends(get_db)):
    """Return this week's training summary: volume, adherence, load trend."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    volume = await weekly_volume_by_discipline(db, monday, today)
    adherence = await get_plan_adherence(db, monday, today)
    load = await training_load_trend(db, weeks=4)

    return {
        "volume": volume,
        "adherence": adherence,
        "load_trend": load,
    }


@router.get("/trends")
async def dashboard_trends(
    start: date | None = Query(default=None, description="Start date (ISO format)"),
    end: date | None = Query(default=None, description="End date (ISO format)"),
    metric: str = Query(default="readiness", description="Metric key for timeseries"),
    db: AsyncSession = Depends(get_db),
):
    """Return configurable trends and summary stats across multiple data types."""
    requested_start = start
    requested_end = end
    window = await trend_data_window(db)
    earliest_data_date = window["earliest_date"]
    latest_data_date = window["latest_date"]

    if end is None:
        end = latest_data_date or date.today()
    if start is None:
        start = end - timedelta(days=30)

    range_adjusted = False
    if earliest_data_date and latest_data_date:
        span_days = max((end - start).days, 1)
        if start > latest_data_date:
            end = latest_data_date
            start = max(earliest_data_date, latest_data_date - timedelta(days=span_days))
            range_adjusted = True
        elif end < earliest_data_date:
            start = earliest_data_date
            end = min(latest_data_date, earliest_data_date + timedelta(days=span_days))
            range_adjusted = True
        else:
            if start < earliest_data_date:
                start = earliest_data_date
                range_adjusted = True
            if end > latest_data_date:
                end = latest_data_date
                range_adjusted = True

    if start > end:
        start = end
        range_adjusted = True

    volume = await weekly_volume_by_discipline(db, start, end)
    stats = await activity_stats(db, start, end)
    activity_types = await activity_type_breakdown(db, start, end)
    metric_data = await daily_metric_trend(db, start, end, metric)
    analysis = await coaching_analysis(db, start, end, volume, stats)
    events = await trend_events(db, start, end)
    coach_summary = build_trend_coach_summary(metric_data, analysis, events)

    executive_end = latest_data_date or date.today()
    executive_start = executive_end - timedelta(days=27)
    executive_volume = await weekly_volume_by_discipline(db, executive_start, executive_end)
    executive_stats = await activity_stats(db, executive_start, executive_end)
    executive_analysis = await coaching_analysis(
        db, executive_start, executive_end, executive_volume, executive_stats
    )

    async def _load_plan_window(window_start: date, window_end: date) -> list[PlannedWorkout]:
        window_result = await db.execute(
            select(PlannedWorkout)
            .where(
                and_(
                    PlannedWorkout.date >= window_start,
                    PlannedWorkout.date <= window_end,
                )
            )
            .order_by(PlannedWorkout.date.asc())
        )
        return list(window_result.scalars().all())

    today_anchor = requested_end or date.today()
    week_start = today_anchor - timedelta(days=today_anchor.weekday())
    week_end = week_start + timedelta(days=6)
    week_workouts = await _load_plan_window(week_start, week_end)
    future_workouts = [workout for workout in week_workouts if workout.date >= today_anchor]
    if not future_workouts:
        next_week_start = week_start + timedelta(days=7)
        next_week_end = next_week_start + timedelta(days=6)
        next_week_workouts = await _load_plan_window(next_week_start, next_week_end)
        if next_week_workouts:
            week_start = next_week_start
            week_end = next_week_end
            week_workouts = next_week_workouts
            future_workouts = list(next_week_workouts)

    week_adherence = await get_plan_adherence(db, week_start, week_end)
    next_sessions = [
        {
            "date": workout.date.isoformat(),
            "label": (
                f"{workout.discipline} {workout.workout_type or workout.description or 'session'}"
                f" {format_planned_duration(workout.target_duration)}"
            ).strip(),
            "status": workout.status,
        }
        for workout in future_workouts
    ][:3]
    plan_week = {
        "start": week_start.isoformat(),
        "end": week_end.isoformat(),
        "total_planned": len(week_workouts),
        "due_so_far": int(week_adherence.get("due_planned", 0)),
        "on_plan_completed": int(week_adherence.get("completed", 0)),
        "remaining": max(0, len(week_workouts) - int(week_adherence.get("completed", 0))),
        "next_sessions": next_sessions,
    }
    latest_summary_result = await db.execute(
        select(GarminDailySummary)
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    latest_summary = latest_summary_result.scalar_one_or_none()
    executive_summary = build_daily_executive_summary(
        executive_end, latest_summary, executive_analysis, plan_week=plan_week
    )

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "requested_start": requested_start.isoformat() if requested_start else None,
        "requested_end": requested_end.isoformat() if requested_end else None,
        "range_adjusted": range_adjusted,
        "earliest_data_date": earliest_data_date.isoformat() if earliest_data_date else None,
        "latest_data_date": latest_data_date.isoformat() if latest_data_date else None,
        "metric": metric_data["metric"],
        "metric_label": metric_data["label"],
        "metric_unit": metric_data["unit"],
        "metric_options": trend_metric_options(),
        "series": metric_data["series"],
        "series_summary": metric_data["summary"],
        "volume": volume,
        "activity_types": activity_types,
        "stats": stats,
        "analysis": analysis,
        "events": events,
        "coach_summary": coach_summary,
        "executive_summary": executive_summary,
        "plan_week": plan_week,
    }
