"""Training plan routes."""

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.models import PlannedWorkout
from src.services.plan_engine import get_current_plan, get_plan_adherence

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
