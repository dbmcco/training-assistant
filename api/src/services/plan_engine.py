"""Plan engine service for training plan management."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import AssistantPlanEntry
from src.db.models import GarminActivity, PlannedWorkout, TrainingPlan
from src.services.assistant_plan import assistant_plan_table_available
from src.services.workout_duration import (
    normalize_planned_duration_minutes,
    planned_duration_seconds,
)


def _normalize_discipline(value: str | None) -> str:
    if not value:
        return "other"
    raw = value.strip().lower()
    if raw.startswith("run") or "trail" in raw:
        return "run"
    if raw.startswith("bike") or "cycl" in raw or "peloton" in raw or "spin" in raw:
        return "bike"
    if raw.startswith("swim") or "pool" in raw or "open_water" in raw:
        return "swim"
    if raw.startswith("strength") or "yoga" in raw or "pilates" in raw:
        return "strength"
    if raw.startswith("walk") or "hike" in raw:
        return "walk"
    if raw in {"cross_training", "cross-training"}:
        return "other"
    return raw or "other"


def _classify_activity_discipline(activity: GarminActivity) -> str:
    text = f"{activity.sport_type or ''} {activity.activity_type or ''}".lower()
    if "run" in text or "trail" in text:
        return "run"
    if "bike" in text or "cycl" in text or "peloton" in text or "spin" in text:
        return "bike"
    if "swim" in text or "pool" in text or "open_water" in text:
        return "swim"
    if "strength" in text or "yoga" in text or "pilates" in text:
        return "strength"
    if "walk" in text or "hike" in text:
        return "walk"
    return "other"


def _activity_date(activity: GarminActivity) -> date | None:
    if activity.start_time is None:
        return None
    return activity.start_time.date()


def _workout_dedupe_key(workout: PlannedWorkout) -> tuple:
    return (
        workout.date,
        _normalize_discipline(workout.discipline),
        (workout.workout_type or "").strip().lower(),
        (workout.description or "").strip().lower(),
        int(normalize_planned_duration_minutes(workout.target_duration) or 0),
        round(float(workout.target_distance or 0.0), 3),
    )


def _status_priority(status: str | None) -> int:
    order = {
        "completed": 6,
        "modified": 5,
        "upcoming": 4,
        "missed": 3,
        "skipped": 2,
    }
    return order.get((status or "").strip().lower(), 1)


def _coerce_created_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _assistant_mode() -> bool:
    return settings.plan_ownership_mode.strip().lower() == "assistant"


def _dedupe_workouts(workouts: list[PlannedWorkout]) -> list[PlannedWorkout]:
    deduped: dict[tuple, PlannedWorkout] = {}
    for workout in workouts:
        key = _workout_dedupe_key(workout)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = workout
            continue

        existing_rank = (
            _coerce_created_at(existing.created_at),
            _status_priority(existing.status),
        )
        current_rank = (
            _coerce_created_at(workout.created_at),
            _status_priority(workout.status),
        )
        if current_rank >= existing_rank:
            deduped[key] = workout
    return list(deduped.values())


def _minimum_expected_seconds(workout: PlannedWorkout) -> float:
    # 60% keeps substitutions realistic while allowing imperfect matches (e.g., 120m plan vs 90m bike).
    duration_seconds = planned_duration_seconds(workout.target_duration)
    if duration_seconds and duration_seconds > 0:
        return max(duration_seconds * 0.6, 10.0 * 60.0)

    defaults_minutes = {
        "run": 20,
        "bike": 30,
        "swim": 20,
        "strength": 15,
        "walk": 20,
        "other": 20,
    }
    discipline = _normalize_discipline(workout.discipline)
    return float(defaults_minutes.get(discipline, 20) * 60)


def _index_activities_by_day_and_discipline(
    activities: list[GarminActivity],
) -> dict[tuple[date, str], list[dict]]:
    buckets: dict[tuple[date, str], list[dict]] = {}
    for activity in activities:
        day = _activity_date(activity)
        if day is None:
            continue
        discipline = _classify_activity_discipline(activity)
        key = (day, discipline)
        bucket = buckets.setdefault(key, [])
        bucket.append(
            {
                "id": str(activity.id),
                "duration_seconds": float(activity.duration_seconds or 0.0),
            }
        )

    for bucket in buckets.values():
        bucket.sort(key=lambda item: item["duration_seconds"], reverse=True)
    return buckets


def _reconcile_due_workouts(
    due_workouts: list[PlannedWorkout],
    activities_by_day_and_discipline: dict[tuple[date, str], list[dict]],
) -> dict[str, int]:
    used_activity_ids: set[str] = set()
    strict_completed = 0
    aligned_substitutions = 0
    missed = 0
    skipped = 0

    for workout in due_workouts:
        status = (workout.status or "").strip().lower()
        if status == "completed":
            strict_completed += 1
            continue

        discipline = _normalize_discipline(workout.discipline)
        expected_seconds = _minimum_expected_seconds(workout)
        bucket = activities_by_day_and_discipline.get((workout.date, discipline), [])

        matched_activity_id: str | None = None
        for candidate in bucket:
            candidate_id = candidate["id"]
            if candidate_id in used_activity_ids:
                continue
            if candidate["duration_seconds"] >= expected_seconds:
                matched_activity_id = candidate_id
                break

        if matched_activity_id is not None:
            used_activity_ids.add(matched_activity_id)
            aligned_substitutions += 1
            continue

        if status == "skipped":
            skipped += 1
        else:
            missed += 1

    return {
        "strict_completed": strict_completed,
        "aligned_substitutions": aligned_substitutions,
        "missed": missed,
        "skipped": skipped,
    }


async def get_today_workout(session: AsyncSession) -> dict | None:
    """Get today's planned workout, if any."""
    query = (
        select(PlannedWorkout)
        .where(PlannedWorkout.date == date.today())
        .order_by(PlannedWorkout.created_at.desc())
        .limit(1)
    )
    if _assistant_mode():
        if not await assistant_plan_table_available(session):
            return None
        query = query.join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )

    result = await session.execute(query)
    workout = result.scalar_one_or_none()
    if not workout:
        return None
    return {
        "id": str(workout.id),
        "date": workout.date.isoformat(),
        "discipline": workout.discipline,
        "workout_type": workout.workout_type,
        "target_duration": normalize_planned_duration_minutes(workout.target_duration),
        "target_distance": workout.target_distance,
        "description": workout.description,
        "status": workout.status,
    }


async def get_upcoming_workouts(
    session: AsyncSession,
    count: int = 5,
) -> list[dict]:
    """Get next N planned workouts from today onwards."""
    query = (
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
    if _assistant_mode():
        if not await assistant_plan_table_available(session):
            return []
        query = query.join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )

    result = await session.execute(query)
    workouts = result.scalars().all()
    return [
        {
            "id": str(w.id),
            "date": w.date.isoformat(),
            "discipline": w.discipline,
            "workout_type": w.workout_type,
            "target_duration": normalize_planned_duration_minutes(w.target_duration),
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
    """Calculate substitution-aware plan adherence for a date range.

    A planned workout is counted as "on plan" when either:
    - it is explicitly marked completed, or
    - a same-day, same-discipline activity exists with enough duration.
    """
    query = select(PlannedWorkout).where(
        and_(
            PlannedWorkout.date >= start,
            PlannedWorkout.date <= end,
        )
    )
    if _assistant_mode():
        if not await assistant_plan_table_available(session):
            return {
                "total_planned": 0,
                "due_planned": 0,
                "pending_future": 0,
                "completed": 0,
                "strict_completed": 0,
                "aligned_substitutions": 0,
                "missed": 0,
                "skipped": 0,
                "completion_pct": 0.0,
                "strict_completion_pct": 0.0,
            }
        query = query.join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )

    workouts_result = await session.execute(query)
    workouts = _dedupe_workouts(list(workouts_result.scalars().all()))
    total_planned = len(workouts)
    if total_planned == 0:
        return {
            "total_planned": 0,
            "due_planned": 0,
            "pending_future": 0,
            "completed": 0,
            "strict_completed": 0,
            "aligned_substitutions": 0,
            "missed": 0,
            "skipped": 0,
            "completion_pct": 0.0,
            "strict_completion_pct": 0.0,
        }

    today = date.today()
    due_cutoff = min(end, today)
    due_workouts = [w for w in workouts if w.date and w.date <= due_cutoff]
    due_planned = len(due_workouts)
    pending_future = max(0, total_planned - due_planned)

    if due_planned == 0:
        return {
            "total_planned": total_planned,
            "due_planned": 0,
            "pending_future": pending_future,
            "completed": 0,
            "strict_completed": 0,
            "aligned_substitutions": 0,
            "missed": 0,
            "skipped": 0,
            "completion_pct": 0.0,
            "strict_completion_pct": 0.0,
        }

    activity_start = datetime(
        start.year, start.month, start.day, tzinfo=timezone.utc
    )
    activity_end = (
        datetime(due_cutoff.year, due_cutoff.month, due_cutoff.day, tzinfo=timezone.utc)
        + timedelta(days=1)
    )

    activity_result = await session.execute(
        select(GarminActivity).where(
            and_(
                GarminActivity.start_time >= activity_start,
                GarminActivity.start_time < activity_end,
            )
        )
    )
    activities = list(activity_result.scalars().all())
    activities_by_day_and_discipline = _index_activities_by_day_and_discipline(
        activities
    )
    reconciliation = _reconcile_due_workouts(
        due_workouts, activities_by_day_and_discipline
    )
    strict_completed = reconciliation["strict_completed"]
    aligned_substitutions = reconciliation["aligned_substitutions"]
    missed = reconciliation["missed"]
    skipped = reconciliation["skipped"]

    completed = strict_completed + aligned_substitutions
    return {
        "total_planned": total_planned,
        "due_planned": due_planned,
        "pending_future": pending_future,
        "completed": completed,
        "strict_completed": strict_completed,
        "aligned_substitutions": aligned_substitutions,
        "missed": missed,
        "skipped": skipped,
        "completion_pct": round(completed / due_planned * 100, 1),
        "strict_completion_pct": round(strict_completed / due_planned * 100, 1),
    }


async def get_current_plan(session: AsyncSession) -> dict | None:
    """Get the active training plan."""
    query = select(TrainingPlan).order_by(TrainingPlan.created_at.desc()).limit(1)
    if _assistant_mode():
        query = select(TrainingPlan).where(TrainingPlan.source == "assistant").order_by(
            TrainingPlan.created_at.desc()
        ).limit(1)
    result = await session.execute(query)
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
