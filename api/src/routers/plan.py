"""Training plan routes."""

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import GarminActivity, PlannedWorkout
from src.services.plan_engine import get_current_plan, get_plan_adherence
from src.services.plan_changes import list_recent_plan_changes

router = APIRouter(prefix="/api/v1/plan", tags=["plan"])


def _workout_to_dict(w: PlannedWorkout) -> dict:
    return {
        "id": str(w.id),
        "plan_id": str(w.plan_id) if w.plan_id else None,
        "date": w.date.isoformat() if w.date else None,
        "discipline": w.discipline,
        "workout_type": w.workout_type,
        "target_duration": w.target_duration,
        "target_distance": w.target_distance,
        "target_hr_zone": w.target_hr_zone,
        "description": w.description,
        "status": w.status,
    }


def _classify_activity_discipline(activity_type: str | None) -> str:
    if not activity_type:
        return "other"
    t = activity_type.lower()
    if "run" in t or "trail" in t:
        return "run"
    if "bike" in t or "cycling" in t:
        return "bike"
    if "swim" in t or "pool" in t:
        return "swim"
    if "walk" in t or "hiking" in t:
        return "walk"
    if "strength" in t:
        return "strength"
    return "other"


def _activity_to_dict(a: GarminActivity) -> dict:
    start_time = a.start_time.isoformat() if a.start_time else None
    activity_date = a.start_time.date().isoformat() if a.start_time else None
    return {
        "id": str(a.id),
        "activity_date": activity_date,
        "start_time": start_time,
        "name": a.name,
        "activity_type": a.activity_type,
        "discipline": _classify_activity_discipline(a.activity_type),
        "duration_seconds": a.duration_seconds,
        "distance_meters": a.distance_meters,
        "average_hr": a.average_hr,
    }


@router.get("/current")
async def current_plan(db: AsyncSession = Depends(get_db)):
    return await get_current_plan(db)


@router.get("/workouts")
async def list_workouts(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    query = select(PlannedWorkout).order_by(PlannedWorkout.date)
    conditions = []
    if start_date:
        conditions.append(PlannedWorkout.date >= start_date)
    if end_date:
        conditions.append(PlannedWorkout.date <= end_date)
    if conditions:
        query = query.where(and_(*conditions))

    result = await db.execute(query)
    workouts = result.scalars().all()
    return [_workout_to_dict(w) for w in workouts]


@router.get("/activities")
async def list_activities(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    query = select(GarminActivity).order_by(GarminActivity.start_time)
    conditions = []
    if start_date:
        start_dt = datetime(
            start_date.year,
            start_date.month,
            start_date.day,
            tzinfo=timezone.utc,
        )
        conditions.append(GarminActivity.start_time >= start_dt)
    if end_date:
        end_dt = (
            datetime(
                end_date.year,
                end_date.month,
                end_date.day,
                tzinfo=timezone.utc,
            )
            + timedelta(days=1)
        )
        conditions.append(GarminActivity.start_time < end_dt)
    if conditions:
        query = query.where(and_(*conditions))

    result = await db.execute(query)
    activities = result.scalars().all()
    return [_activity_to_dict(a) for a in activities]


@router.put("/workouts/{workout_id}")
async def update_workout(
    workout_id: UUID, body: dict, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PlannedWorkout).where(PlannedWorkout.id == workout_id)
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    for field in (
        "date",
        "discipline",
        "workout_type",
        "target_duration",
        "target_distance",
        "target_hr_zone",
        "description",
        "status",
    ):
        if field in body:
            value = body[field]
            if field == "date" and isinstance(value, str):
                value = date.fromisoformat(value)
            setattr(workout, field, value)

    await db.commit()
    await db.refresh(workout)
    return _workout_to_dict(workout)


@router.get("/adherence")
async def plan_adherence(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=28)
    return await get_plan_adherence(db, start, end)


@router.get("/changes")
async def plan_changes(
    days_back: int = Query(default=7, ge=1, le=60),
    limit: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await list_recent_plan_changes(
        db,
        days_back=days_back,
        limit=limit,
    )
