"""Plan engine service for training plan management."""

from datetime import date

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import PlannedWorkout, TrainingPlan


async def get_today_workout(session: AsyncSession) -> dict | None:
    """Get today's planned workout, if any."""
    result = await session.execute(
        select(PlannedWorkout)
        .where(PlannedWorkout.date == date.today())
        .limit(1)
    )
    workout = result.scalar_one_or_none()
    if not workout:
        return None
    return {
        "id": str(workout.id),
        "date": workout.date.isoformat(),
        "discipline": workout.discipline,
        "workout_type": workout.workout_type,
        "target_duration": workout.target_duration,
        "target_distance": workout.target_distance,
        "description": workout.description,
        "status": workout.status,
    }


async def get_upcoming_workouts(
    session: AsyncSession,
    count: int = 5,
) -> list[dict]:
    """Get next N planned workouts from today onwards."""
    result = await session.execute(
        select(PlannedWorkout)
        .where(
            and_(
                PlannedWorkout.date >= date.today(),
                PlannedWorkout.status.in_(["upcoming", "modified"]),
            )
        )
        .order_by(PlannedWorkout.date)
        .limit(count)
    )
    workouts = result.scalars().all()
    return [
        {
            "id": str(w.id),
            "date": w.date.isoformat(),
            "discipline": w.discipline,
            "workout_type": w.workout_type,
            "target_duration": w.target_duration,
            "description": w.description,
            "status": w.status,
        }
        for w in workouts
    ]


async def get_plan_adherence(
    session: AsyncSession,
    start: date,
    end: date,
) -> dict:
    """Calculate plan adherence for a date range."""
    result = await session.execute(
        select(
            func.count().label("total"),
            func.count().filter(PlannedWorkout.status == "completed").label("completed"),
            func.count().filter(PlannedWorkout.status == "missed").label("missed"),
            func.count().filter(PlannedWorkout.status == "skipped").label("skipped"),
        )
        .where(
            and_(
                PlannedWorkout.date >= start,
                PlannedWorkout.date <= end,
            )
        )
    )
    row = result.one()
    total = row.total or 0
    completed = row.completed or 0
    return {
        "total_planned": total,
        "completed": completed,
        "missed": row.missed or 0,
        "skipped": row.skipped or 0,
        "completion_pct": round(completed / total * 100, 1) if total > 0 else 0.0,
    }


async def get_current_plan(session: AsyncSession) -> dict | None:
    """Get the active training plan."""
    result = await session.execute(
        select(TrainingPlan)
        .order_by(TrainingPlan.created_at.desc())
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return None
    return {
        "id": str(plan.id),
        "name": plan.name,
        "source": plan.source,
        "start_date": plan.start_date.isoformat() if plan.start_date else None,
        "end_date": plan.end_date.isoformat() if plan.end_date else None,
    }
