"""Plan change tracking for adaptive Garmin workout updates."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import PlanChangeEvent, PlannedWorkout
from src.services.garmin_refresh import refresh_garmin_daily_data_on_demand

SNAPSHOT_FIELDS = (
    "date",
    "discipline",
    "workout_type",
    "target_duration",
    "target_distance",
    "target_hr_zone",
    "description",
    "status",
)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _snapshot_workout(workout: PlannedWorkout) -> dict[str, Any]:
    return {
        "id": str(workout.id),
        "date": workout.date.isoformat() if workout.date else None,
        "discipline": _clean_text(workout.discipline.lower() if workout.discipline else None),
        "workout_type": _clean_text(workout.workout_type.lower() if workout.workout_type else None),
        "target_duration": int(workout.target_duration) if workout.target_duration is not None else None,
        "target_distance": round(float(workout.target_distance), 2)
        if workout.target_distance is not None
        else None,
        "target_hr_zone": int(workout.target_hr_zone) if workout.target_hr_zone is not None else None,
        "description": _clean_text(workout.description.lower() if workout.description else None),
        "status": _clean_text(workout.status.lower() if workout.status else None),
    }


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _coerce_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _format_label(value: str | None) -> str:
    if not value:
        return "workout"
    return value.replace("_", " ").strip()


def summarize_plan_change(
    *,
    event_type: str,
    workout_date: date | None,
    previous_workout_date: date | None,
    discipline: str | None,
    workout_type: str | None,
    changed_fields: list[str] | None = None,
) -> str:
    discipline_label = _format_label(discipline)
    workout_label = _format_label(workout_type)
    date_label = workout_date.isoformat() if workout_date else "unknown date"

    if event_type == "rescheduled":
        prev = previous_workout_date.isoformat() if previous_workout_date else "unknown date"
        return f"Moved {discipline_label} {workout_label} from {prev} to {date_label}."
    if event_type == "added":
        return f"Added {discipline_label} {workout_label} on {date_label}."
    if event_type == "removed":
        return f"Removed {discipline_label} {workout_label} from {date_label}."

    fields = changed_fields or []
    if fields:
        pretty_fields = ", ".join(field.replace("_", " ") for field in fields)
        return f"Updated {pretty_fields} for {discipline_label} {workout_label} on {date_label}."
    return f"Updated {discipline_label} {workout_label} on {date_label}."


def diff_plan_snapshots(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    before_ids = set(before.keys())
    after_ids = set(after.keys())

    for workout_id in sorted(before_ids - after_ids):
        old = before[workout_id]
        events.append(
            {
                "event_type": "removed",
                "workout_id": workout_id,
                "workout_date": _parse_iso_date(old.get("date")),
                "previous_workout_date": _parse_iso_date(old.get("date")),
                "discipline": old.get("discipline"),
                "workout_type": old.get("workout_type"),
                "changed_fields": [],
                "previous_values": old,
                "new_values": None,
            }
        )

    for workout_id in sorted(after_ids - before_ids):
        new = after[workout_id]
        events.append(
            {
                "event_type": "added",
                "workout_id": workout_id,
                "workout_date": _parse_iso_date(new.get("date")),
                "previous_workout_date": None,
                "discipline": new.get("discipline"),
                "workout_type": new.get("workout_type"),
                "changed_fields": [],
                "previous_values": None,
                "new_values": new,
            }
        )

    for workout_id in sorted(before_ids & after_ids):
        old = before[workout_id]
        new = after[workout_id]
        changed = [field for field in SNAPSHOT_FIELDS if old.get(field) != new.get(field)]
        if not changed:
            continue

        event_type = "rescheduled" if "date" in changed else "updated"
        events.append(
            {
                "event_type": event_type,
                "workout_id": workout_id,
                "workout_date": _parse_iso_date(new.get("date")),
                "previous_workout_date": _parse_iso_date(old.get("date")),
                "discipline": new.get("discipline") or old.get("discipline"),
                "workout_type": new.get("workout_type") or old.get("workout_type"),
                "changed_fields": changed,
                "previous_values": old,
                "new_values": new,
            }
        )

    def _sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
        detected_date = item.get("workout_date") or item.get("previous_workout_date")
        date_key = detected_date.isoformat() if isinstance(detected_date, date) else "9999-12-31"
        return (date_key, item.get("event_type", ""), str(item.get("workout_id", "")))

    events.sort(key=_sort_key)
    return events


def _event_with_summary(event: dict[str, Any]) -> dict[str, Any]:
    changed_fields = list(event.get("changed_fields") or [])
    summary = summarize_plan_change(
        event_type=str(event.get("event_type") or "updated"),
        workout_date=event.get("workout_date"),
        previous_workout_date=event.get("previous_workout_date"),
        discipline=event.get("discipline"),
        workout_type=event.get("workout_type"),
        changed_fields=changed_fields,
    )
    return {
        **event,
        "changed_fields": changed_fields,
        "summary": summary,
    }


async def capture_upcoming_plan_snapshot(
    db: AsyncSession,
    *,
    horizon_days: int = 21,
    max_rows: int = 600,
) -> dict[str, dict[str, Any]]:
    await _ensure_snapshot_indexes(db)

    start = date.today()
    end = start + timedelta(days=max(horizon_days, 1))

    result = await db.execute(
        select(
            PlannedWorkout.id,
            PlannedWorkout.date,
            PlannedWorkout.discipline,
            PlannedWorkout.workout_type,
            PlannedWorkout.target_duration,
            PlannedWorkout.target_distance,
            PlannedWorkout.target_hr_zone,
            PlannedWorkout.description,
            PlannedWorkout.status,
        )
        .where(
            and_(
                PlannedWorkout.date >= start,
                PlannedWorkout.date <= end,
                PlannedWorkout.status.in_(["upcoming", "modified"]),
            )
        )
        .order_by(PlannedWorkout.date.asc())
        .limit(max(50, max_rows))
    )
    rows = result.all()

    snapshot: dict[str, dict[str, Any]] = {}
    for row in rows:
        workout = PlannedWorkout(
            id=row.id,
            date=row.date,
            discipline=row.discipline,
            workout_type=row.workout_type,
            target_duration=row.target_duration,
            target_distance=row.target_distance,
            target_hr_zone=row.target_hr_zone,
            description=row.description,
            status=row.status,
        )
        snapshot[str(row.id)] = _snapshot_workout(workout)
    return snapshot


async def persist_plan_change_events(
    db: AsyncSession,
    *,
    events: list[dict[str, Any]],
    source: str,
    detected_at: datetime | None = None,
) -> list[PlanChangeEvent]:
    if not events:
        return []

    await _ensure_plan_change_table(db)

    now = detected_at or datetime.now(timezone.utc)
    rows: list[PlanChangeEvent] = []
    for event in events:
        changed_fields = event.get("changed_fields") or []
        row = PlanChangeEvent(
            source=source,
            event_type=str(event.get("event_type") or "updated"),
            workout_id=_coerce_uuid(event.get("workout_id")),
            workout_date=event.get("workout_date"),
            previous_workout_date=event.get("previous_workout_date"),
            discipline=event.get("discipline"),
            workout_type=event.get("workout_type"),
            changed_fields=changed_fields,
            previous_values=event.get("previous_values"),
            new_values=event.get("new_values"),
            detected_at=now,
        )
        rows.append(row)
        db.add(row)

    await db.flush()
    return rows


def serialize_plan_change_event(row: PlanChangeEvent) -> dict[str, Any]:
    changed_fields = list(row.changed_fields or [])
    summary = summarize_plan_change(
        event_type=row.event_type,
        workout_date=row.workout_date,
        previous_workout_date=row.previous_workout_date,
        discipline=row.discipline,
        workout_type=row.workout_type,
        changed_fields=changed_fields,
    )
    return {
        "id": str(row.id),
        "source": row.source,
        "event_type": row.event_type,
        "workout_id": str(row.workout_id) if row.workout_id else None,
        "workout_date": row.workout_date.isoformat() if row.workout_date else None,
        "previous_workout_date": row.previous_workout_date.isoformat()
        if row.previous_workout_date
        else None,
        "discipline": row.discipline,
        "workout_type": row.workout_type,
        "changed_fields": changed_fields,
        "previous_values": row.previous_values,
        "new_values": row.new_values,
        "detected_at": row.detected_at.isoformat() if row.detected_at else None,
        "summary": summary,
    }


async def list_recent_plan_changes(
    db: AsyncSession,
    *,
    days_back: int = 7,
    limit: int = 25,
) -> list[dict[str, Any]]:
    await _ensure_plan_change_table(db)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(days_back, 1))
    result = await db.execute(
        select(PlanChangeEvent)
        .where(PlanChangeEvent.detected_at >= cutoff)
        .order_by(PlanChangeEvent.detected_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    rows = result.scalars().all()
    return [serialize_plan_change_event(row) for row in rows]


async def refresh_with_plan_change_tracking(
    db: AsyncSession,
    *,
    include_calendar: bool = False,
    force: bool = False,
    source: str = "garmin_refresh",
    horizon_days: int = 21,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    before_snapshot: dict[str, dict[str, Any]] = {}
    if include_calendar:
        before_snapshot = await capture_upcoming_plan_snapshot(
            db, horizon_days=horizon_days
        )

    result = await refresh_garmin_daily_data_on_demand(
        include_calendar=include_calendar,
        force=force,
    )

    events: list[dict[str, Any]] = []
    if include_calendar and result.get("status") == "success":
        after_snapshot = await capture_upcoming_plan_snapshot(
            db, horizon_days=horizon_days
        )
        events = [_event_with_summary(event) for event in diff_plan_snapshots(before_snapshot, after_snapshot)]
        if events:
            await persist_plan_change_events(db, events=events, source=source)
            await db.commit()

    return result, events


async def _ensure_plan_change_table(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS plan_change_events (
                id UUID PRIMARY KEY,
                source TEXT NOT NULL,
                event_type TEXT NOT NULL,
                workout_id UUID NULL,
                workout_date DATE NULL,
                previous_workout_date DATE NULL,
                discipline TEXT NULL,
                workout_type TEXT NULL,
                changed_fields JSONB NULL,
                previous_values JSONB NULL,
                new_values JSONB NULL,
                detected_at TIMESTAMPTZ NULL
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_plan_change_events_detected_at
                ON plan_change_events (detected_at)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_plan_change_events_workout_date
                ON plan_change_events (workout_date)
            """
        )
    )


async def _ensure_snapshot_indexes(db: AsyncSession) -> None:
    await db.execute(text("SET LOCAL statement_timeout = 0"))
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_planned_workouts_date_status
                ON planned_workouts (date, status)
            """
        )
    )
