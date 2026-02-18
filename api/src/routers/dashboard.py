"""Dashboard API routes for the Training Assistant."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import DailyBriefing, GarminDailySummary, Race
from src.services.analytics import (
    activity_stats,
    training_load_trend,
    weekly_volume_by_discipline,
)
from src.services.plan_engine import (
    get_plan_adherence,
    get_today_workout,
)
from src.services.readiness import compute_readiness

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/today")
async def dashboard_today(db: AsyncSession = Depends(get_db)):
    """Return today's dashboard snapshot: readiness, workout, races, briefing, metrics."""
    today = date.today()

    # Get the latest GarminDailySummary (may not be exactly today)
    summary_result = await db.execute(
        select(GarminDailySummary)
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    summary = summary_result.scalar_one_or_none()

    # Compute readiness from the latest summary
    if summary:
        readiness = compute_readiness(
            hrv_last_night=summary.hrv_last_night,
            hrv_7d_avg=summary.hrv_7d_avg,
            sleep_score=summary.sleep_score,
            body_battery_wake=summary.body_battery_at_wake,
            recovery_time_hours=summary.recovery_time_hours,
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
        training_status = summary.training_status
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
        briefing = {
            "content": briefing_row.content,
            "readiness_summary": briefing_row.readiness_summary,
            "workout_recommendation": briefing_row.workout_recommendation,
            "alerts": briefing_row.alerts,
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
    metric: str | None = Query(default=None, description="Optional metric filter"),
    db: AsyncSession = Depends(get_db),
):
    """Return configurable date range trends with volume and activity stats."""
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=30)

    volume = await weekly_volume_by_discipline(db, start, end)
    stats = await activity_stats(db, start, end)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "metric": metric,
        "volume": volume,
        "stats": stats,
    }
