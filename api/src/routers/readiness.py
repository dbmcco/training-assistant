"""Readiness score routes."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import GarminDailySummary
from src.services.readiness import compute_readiness

router = APIRouter(prefix="/api/v1/readiness", tags=["readiness"])


@router.get("/today")
async def readiness_today(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GarminDailySummary)
        .order_by(GarminDailySummary.calendar_date.desc())
        .limit(1)
    )
    summary = result.scalar_one_or_none()

    if not summary:
        return {"score": 50, "label": "Moderate", "components": []}

    readiness = compute_readiness(
        hrv_last_night=summary.hrv_last_night,
        hrv_7d_avg=summary.hrv_7d_avg,
        sleep_score=summary.sleep_score,
        body_battery_wake=summary.body_battery_at_wake,
        recovery_time_hours=summary.recovery_time_hours,
        training_load_7d=summary.training_load_7d,
        training_load_28d=summary.training_load_28d,
    )

    return {
        "date": summary.calendar_date.isoformat(),
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


@router.get("/history")
async def readiness_history(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    start = date.today() - timedelta(days=days)
    result = await db.execute(
        select(GarminDailySummary)
        .where(GarminDailySummary.calendar_date > start)
        .order_by(GarminDailySummary.calendar_date.desc())
    )
    summaries = result.scalars().all()

    history = []
    for s in summaries:
        readiness = compute_readiness(
            hrv_last_night=s.hrv_last_night,
            hrv_7d_avg=s.hrv_7d_avg,
            sleep_score=s.sleep_score,
            body_battery_wake=s.body_battery_at_wake,
            recovery_time_hours=s.recovery_time_hours,
            training_load_7d=s.training_load_7d,
            training_load_28d=s.training_load_28d,
        )
        history.append({
            "date": s.calendar_date.isoformat(),
            "score": readiness.score,
            "label": readiness.label,
        })

    return history
