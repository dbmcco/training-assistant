"""Assistant-owned plan generation and sync orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import AssistantPlanEntry, PlannedWorkout, Race, TrainingPlan
from src.services.garmin_writeback import (
    fallback_writeback_payload,
    write_recommendation_change,
)


def is_assistant_owned_mode() -> bool:
    return settings.plan_ownership_mode.strip().lower() == "assistant"


async def assistant_plan_table_available(db: AsyncSession) -> bool:
    result = await db.execute(
        text("SELECT to_regclass('public.assistant_plan_entries')")
    )
    return result.scalar_one_or_none() is not None


async def ensure_assistant_plan_table(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS assistant_plan_entries (
                id UUID PRIMARY KEY,
                planned_workout_id UUID NOT NULL UNIQUE REFERENCES planned_workouts(id),
                is_locked BOOLEAN NOT NULL DEFAULT FALSE,
                garmin_workout_id TEXT NULL,
                garmin_sync_status TEXT NULL,
                garmin_sync_result JSONB NULL,
                created_at TIMESTAMPTZ NULL,
                updated_at TIMESTAMPTZ NULL
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_assistant_plan_entries_created_at
                ON assistant_plan_entries (created_at)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_assistant_plan_entries_is_locked
                ON assistant_plan_entries (is_locked)
            """
        )
    )


@dataclass(frozen=True)
class DayTemplate:
    discipline: str
    workout_type: str
    duration_min: int
    description: str


def _phase_label(days_to_race: int | None) -> str:
    if days_to_race is None:
        return "base"
    if days_to_race <= 14:
        return "taper"
    if days_to_race <= 42:
        return "peak"
    if days_to_race <= 84:
        return "build"
    return "base"


def _template_for_day(
    *,
    day: date,
    phase: str,
    week_index: int,
) -> DayTemplate | None:
    weekday = day.weekday()  # Mon=0..Sun=6

    # Keep predictable structure; agent can later modify day-by-day with approvals.
    if weekday == 0:
        return DayTemplate(
            discipline="strength",
            workout_type="mobility_strength",
            duration_min=35,
            description="Mobility + functional strength. Keep it crisp and controlled.",
        )
    if weekday == 1:
        return DayTemplate(
            discipline="bike",
            workout_type="quality_intervals",
            duration_min=70 if phase in {"build", "peak"} else 60,
            description="Bike quality set. Controlled hard work with full recoveries.",
        )
    if weekday == 2:
        return DayTemplate(
            discipline="run",
            workout_type="endurance_run",
            duration_min=55 if phase in {"build", "peak"} else 45,
            description="Aerobic endurance run. Steady effort, no racing.",
        )
    if weekday == 3:
        return DayTemplate(
            discipline="swim",
            workout_type="endurance_builder",
            duration_min=50,
            description="Swim endurance + form focus. Maintain relaxed technique under load.",
        )
    if weekday == 4:
        return DayTemplate(
            discipline="bike",
            workout_type="easy_spin",
            duration_min=50,
            description="Easy spin and leg turnover. Keep intensity low.",
        )
    if weekday == 5:
        long_run = 75 + (10 * min(week_index, 4))
        if phase == "taper":
            long_run = 55
        if phase == "peak":
            long_run = min(long_run + 10, 120)
        return DayTemplate(
            discipline="run",
            workout_type="long_run",
            duration_min=long_run,
            description="Long aerobic run. Smooth pacing and fueling practice.",
        )
    if weekday == 6:
        long_ride = 120 + (15 * min(week_index, 4))
        if phase == "taper":
            long_ride = 75
        if phase == "peak":
            long_ride = min(long_ride + 15, 210)
        return DayTemplate(
            discipline="bike",
            workout_type="long_ride",
            duration_min=long_ride,
            description="Long ride with race-day fueling and cadence discipline.",
        )
    return None


async def _upcoming_race(db: AsyncSession) -> Race | None:
    result = await db.execute(
        select(Race)
        .where(Race.date >= date.today())
        .order_by(Race.date.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _ensure_assistant_training_plan(
    db: AsyncSession,
    *,
    start: date,
    end: date,
    race: Race | None,
) -> TrainingPlan:
    result = await db.execute(
        select(TrainingPlan)
        .where(TrainingPlan.source == "assistant")
        .order_by(TrainingPlan.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing and existing.end_date and existing.end_date >= end:
        return existing

    now = datetime.now(timezone.utc)
    plan_name = f"Assistant Rolling Plan ({start.isoformat()})"
    new_plan = TrainingPlan(
        race_id=race.id if race else None,
        name=plan_name,
        source="assistant",
        start_date=start,
        end_date=end,
        created_at=now,
    )
    db.add(new_plan)
    await db.flush()
    return new_plan


async def _delete_existing_assistant_window(
    db: AsyncSession,
    *,
    start: date,
) -> int:
    if not await assistant_plan_table_available(db):
        return 0

    result = await db.execute(
        select(PlannedWorkout.id)
        .join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
        .where(PlannedWorkout.date >= start)
    )
    ids = [row[0] for row in result.all()]
    if not ids:
        return 0

    await db.execute(
        delete(AssistantPlanEntry).where(
            AssistantPlanEntry.planned_workout_id.in_(ids)
        )
    )
    deleted = await db.execute(
        delete(PlannedWorkout).where(PlannedWorkout.id.in_(ids))
    )
    return int(deleted.rowcount or 0)


async def generate_assistant_plan(
    db: AsyncSession,
    *,
    days_ahead: int | None = None,
    overwrite: bool = True,
    sync_to_garmin: bool = True,
) -> dict[str, Any]:
    if not is_assistant_owned_mode():
        raise ValueError("Assistant-owned plan mode is not enabled.")

    await ensure_assistant_plan_table(db)

    today = date.today()
    horizon = max(days_ahead or settings.assistant_plan_default_days_ahead, 3)
    end = today + timedelta(days=horizon - 1)
    race = await _upcoming_race(db)
    days_to_race = (race.date - today).days if race else None
    phase = _phase_label(days_to_race)
    lock_window = max(settings.assistant_plan_lock_window_days, 1)
    sync_window = max(settings.assistant_plan_sync_days, 0)
    sync_cutoff = today + timedelta(days=max(sync_window - 1, 0))

    plan = await _ensure_assistant_training_plan(
        db,
        start=today,
        end=end,
        race=race,
    )

    deleted_count = 0
    if overwrite:
        deleted_count = await _delete_existing_assistant_window(db, start=today)

    now = datetime.now(timezone.utc)
    created_rows: list[tuple[PlannedWorkout, AssistantPlanEntry]] = []
    for offset in range(horizon):
        session_day = today + timedelta(days=offset)
        week_index = offset // 7
        template = _template_for_day(
            day=session_day,
            phase=phase,
            week_index=week_index,
        )
        if template is None:
            continue

        workout = PlannedWorkout(
            plan_id=plan.id,
            date=session_day,
            discipline=template.discipline,
            workout_type=template.workout_type,
            target_duration=template.duration_min,
            description=template.description,
            status="upcoming",
            created_at=now,
        )
        db.add(workout)
        await db.flush()

        entry = AssistantPlanEntry(
            planned_workout_id=workout.id,
            is_locked=session_day <= today + timedelta(days=lock_window - 1),
            garmin_sync_status="pending" if sync_to_garmin else "skipped",
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
        created_rows.append((workout, entry))

    synced_success = 0
    synced_failed = 0
    synced_skipped = 0
    if sync_to_garmin:
        for workout, entry in created_rows:
            if workout.date and workout.date > sync_cutoff:
                entry.garmin_sync_status = "skipped_out_of_window"
                entry.updated_at = datetime.now(timezone.utc)
                synced_skipped += 1
                continue

            payload = fallback_writeback_payload(
                workout_date=workout.date.isoformat() if workout.date else None,
                discipline=workout.discipline,
                workout_type=workout.workout_type,
                target_duration=workout.target_duration,
                description=workout.description,
                recommendation_text=(
                    f"Assistant-owned plan sync ({phase})"
                ),
            )
            result = await write_recommendation_change(payload)
            status = str(result.get("status", "failed")).lower()
            entry.garmin_sync_result = result
            entry.updated_at = datetime.now(timezone.utc)
            if status == "success":
                entry.garmin_workout_id = str(result.get("workout_id") or "")
                entry.garmin_sync_status = "success"
                synced_success += 1
            else:
                entry.garmin_sync_status = "failed"
                synced_failed += 1

    await db.flush()

    return {
        "mode": settings.plan_ownership_mode,
        "phase": phase,
        "race": (
            {
                "id": str(race.id),
                "name": race.name,
                "date": race.date.isoformat(),
                "distance_type": race.distance_type,
                "days_to_race": days_to_race,
            }
            if race
            else None
        ),
        "window_start": today.isoformat(),
        "window_end": end.isoformat(),
        "days_ahead": horizon,
        "plan_id": str(plan.id),
        "deleted_existing": deleted_count,
        "created_workouts": len(created_rows),
        "synced_success": synced_success,
        "synced_failed": synced_failed,
        "synced_skipped": synced_skipped,
        "workouts": [
            {
                "id": str(workout.id),
                "date": workout.date.isoformat() if workout.date else None,
                "discipline": workout.discipline,
                "workout_type": workout.workout_type,
                "target_duration": workout.target_duration,
                "status": workout.status,
                "is_locked": entry.is_locked,
                "garmin_sync_status": entry.garmin_sync_status,
                "garmin_workout_id": entry.garmin_workout_id,
            }
            for workout, entry in created_rows
        ],
    }


async def list_assistant_workout_ids_for_range(
    db: AsyncSession,
    *,
    start: date,
    end: date,
) -> list[str]:
    if not await assistant_plan_table_available(db):
        return []
    result = await db.execute(
        select(PlannedWorkout.id)
        .join(
            AssistantPlanEntry,
            AssistantPlanEntry.planned_workout_id == PlannedWorkout.id,
        )
        .where(
            and_(
                PlannedWorkout.date >= start,
                PlannedWorkout.date <= end,
            )
        )
    )
    return [str(row[0]) for row in result.all()]
