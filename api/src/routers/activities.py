"""Activity routes."""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import GarminActivity
from src.services.analytics import activity_stats as compute_activity_stats

router = APIRouter(prefix="/api/v1/activities", tags=["activities"])


def _activity_to_dict(a: GarminActivity) -> dict:
    return {
        "id": str(a.id),
        "garmin_activity_id": a.garmin_activity_id,
        "name": a.name,
        "activity_type": a.activity_type,
        "sport_type": a.sport_type,
        "start_time": a.start_time.isoformat() if a.start_time else None,
        "distance_meters": a.distance_meters,
        "duration_seconds": a.duration_seconds,
        "elevation_gain_meters": a.elevation_gain_meters,
        "calories": a.calories,
        "average_hr": a.average_hr,
        "max_hr": a.max_hr,
        "aerobic_training_effect": a.aerobic_training_effect,
        "anaerobic_training_effect": a.anaerobic_training_effect,
    }


@router.get("")
async def list_activities(
    discipline: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(GarminActivity).order_by(GarminActivity.start_time.desc())
    conditions = []

    if discipline:
        conditions.append(GarminActivity.activity_type == discipline)
    if start_date:
        start_dt = datetime(
            start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc
        )
        conditions.append(GarminActivity.start_time >= start_dt)
    if end_date:
        end_dt = datetime(
            end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc
        ) + timedelta(days=1)
        conditions.append(GarminActivity.start_time < end_dt)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    activities = result.scalars().all()
    return [_activity_to_dict(a) for a in activities]


@router.get("/stats")
async def activity_stats_route(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=30)
    return await compute_activity_stats(db, start, end)


@router.get("/{garmin_activity_id}")
async def get_activity(garmin_activity_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GarminActivity).where(
            GarminActivity.garmin_activity_id == garmin_activity_id
        )
    )
    activity = result.scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return _activity_to_dict(activity)
