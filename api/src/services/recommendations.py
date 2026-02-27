"""Recommendation change lifecycle helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DailyBriefing, PlannedWorkout, RecommendationChange
from src.services.garmin_refresh import refresh_garmin_daily_data_on_demand
from src.services.garmin_writeback import (
    fallback_writeback_payload,
    write_recommendation_change,
)

ALLOWED_DECISIONS = {"approved", "rejected", "changes_requested"}


async def recommendation_table_available(db: AsyncSession) -> bool:
    """Return True if recommendation_changes exists in the connected DB."""
    result = await db.execute(text("SELECT to_regclass('public.recommendation_changes')"))
    return result.scalar_one_or_none() is not None


def _parse_uuid(value: Any) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _normalise_discipline(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip().lower()
    if raw.startswith("run"):
        return "run"
    if raw.startswith("bike") or "cycl" in raw:
        return "bike"
    if raw.startswith("swim"):
        return "swim"
    if raw.startswith("strength"):
        return "strength"
    if raw:
        return raw
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _workout_snapshot(workout: PlannedWorkout | None) -> dict[str, Any] | None:
    if not workout:
        return None
    return {
        "id": str(workout.id),
        "date": workout.date.isoformat() if workout.date else None,
        "discipline": workout.discipline,
        "workout_type": workout.workout_type,
        "target_duration": workout.target_duration,
        "target_distance": workout.target_distance,
        "target_hr_zone": workout.target_hr_zone,
        "description": workout.description,
        "status": workout.status,
    }


def _append_event(
    rec: RecommendationChange,
    *,
    event: str,
    payload: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    log = rec.training_impact_log or {}
    events = list(log.get("events", []))
    events.append({"at": now, "event": event, **(payload or {})})
    rec.training_impact_log = {**log, "events": events}


def _sanitize_proposed_workout(raw_change: Any) -> dict[str, Any]:
    if not isinstance(raw_change, dict):
        return {}
    parsed_workout_date = _parse_date(raw_change.get("workout_date"))
    return {
        "workout_id": str(raw_change.get("workout_id")).strip() if raw_change.get("workout_id") else None,
        "workout_date": parsed_workout_date.isoformat() if parsed_workout_date else None,
        "discipline": _normalise_discipline(raw_change.get("discipline")),
        "workout_type": str(raw_change.get("workout_type")).strip() if raw_change.get("workout_type") else None,
        "target_duration": _coerce_int(raw_change.get("target_duration")),
        "description": str(raw_change.get("description")).strip() if raw_change.get("description") else None,
        "reason": str(raw_change.get("reason")).strip() if raw_change.get("reason") else None,
    }


def _needs_change(raw_change: Any, recommendation_text: str | None) -> bool:
    if isinstance(raw_change, dict) and isinstance(raw_change.get("needs_change"), bool):
        return bool(raw_change["needs_change"])
    text = (recommendation_text or "").lower()
    if not text:
        return False
    keep_tokens = ("no change", "as planned", "keep", "confirm today's", "confirm today")
    return not any(token in text for token in keep_tokens)


async def _find_target_workout(
    db: AsyncSession,
    *,
    workout_id: UUID | None,
    workout_date: date | None,
    discipline: str | None,
) -> PlannedWorkout | None:
    if workout_id:
        by_id = await db.execute(select(PlannedWorkout).where(PlannedWorkout.id == workout_id))
        row = by_id.scalar_one_or_none()
        if row:
            return row

    if not workout_date:
        return None

    query = select(PlannedWorkout).where(PlannedWorkout.date == workout_date)
    if discipline:
        query = query.where(PlannedWorkout.discipline.ilike(f"%{discipline}%"))
    query = query.order_by(PlannedWorkout.created_at.desc(), PlannedWorkout.id)
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none()


def serialize_recommendation(rec: RecommendationChange) -> dict[str, Any]:
    return {
        "id": str(rec.id),
        "source": rec.source,
        "source_ref_id": str(rec.source_ref_id) if rec.source_ref_id else None,
        "planned_workout_id": str(rec.planned_workout_id) if rec.planned_workout_id else None,
        "workout_date": rec.workout_date.isoformat() if rec.workout_date else None,
        "recommendation_text": rec.recommendation_text,
        "proposed_workout": rec.proposed_workout,
        "status": rec.status,
        "decision_notes": rec.decision_notes,
        "requested_changes": rec.requested_changes,
        "garmin_sync_status": rec.garmin_sync_status,
        "garmin_sync_payload": rec.garmin_sync_payload,
        "garmin_sync_result": rec.garmin_sync_result,
        "training_impact_log": rec.training_impact_log,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "decided_at": rec.decided_at.isoformat() if rec.decided_at else None,
        "applied_at": rec.applied_at.isoformat() if rec.applied_at else None,
    }


async def get_briefing_recommendation(
    db: AsyncSession, briefing_id: UUID
) -> RecommendationChange | None:
    if not await recommendation_table_available(db):
        return None
    result = await db.execute(
        select(RecommendationChange)
        .where(
            and_(
                RecommendationChange.source == "briefing",
                RecommendationChange.source_ref_id == briefing_id,
            )
        )
        .order_by(RecommendationChange.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_recommendation_from_briefing(
    db: AsyncSession,
    *,
    briefing: DailyBriefing,
    parsed_payload: dict[str, Any],
) -> RecommendationChange | None:
    if not await recommendation_table_available(db):
        return None

    if not briefing.id:
        return None

    existing = await get_briefing_recommendation(db, briefing.id)
    if existing:
        return existing

    recommendation_text = parsed_payload.get("workout_recommendation")
    raw_change = parsed_payload.get("recommendation_change")
    if not _needs_change(raw_change, recommendation_text):
        return None

    proposed = _sanitize_proposed_workout(raw_change)
    workout_id = _parse_uuid(proposed.get("workout_id"))
    workout_date = _parse_date(proposed.get("workout_date")) or briefing.date
    discipline = _normalise_discipline(proposed.get("discipline"))

    target_workout = await _find_target_workout(
        db,
        workout_id=workout_id,
        workout_date=workout_date,
        discipline=discipline,
    )

    now = datetime.now(timezone.utc)
    rec = RecommendationChange(
        source="briefing",
        source_ref_id=briefing.id,
        planned_workout_id=target_workout.id if target_workout else None,
        workout_date=workout_date,
        recommendation_text=recommendation_text,
        proposed_workout=proposed,
        status="pending",
        garmin_sync_status="pending",
        created_at=now,
    )
    _append_event(
        rec,
        event="created",
        payload={
            "recommendation_text": recommendation_text,
            "target_workout": _workout_snapshot(target_workout),
        },
    )
    db.add(rec)
    await db.flush()
    return rec


def _apply_proposed_workout(workout: PlannedWorkout, proposed: dict[str, Any]) -> None:
    new_date = _parse_date(proposed.get("workout_date"))
    if new_date:
        workout.date = new_date

    new_discipline = _normalise_discipline(proposed.get("discipline"))
    if new_discipline:
        workout.discipline = new_discipline

    if proposed.get("workout_type"):
        workout.workout_type = str(proposed.get("workout_type")).strip()

    new_duration = _coerce_int(proposed.get("target_duration"))
    if new_duration is not None and new_duration > 0:
        workout.target_duration = new_duration

    if proposed.get("description"):
        workout.description = str(proposed.get("description")).strip()


async def decide_recommendation(
    db: AsyncSession,
    *,
    recommendation: RecommendationChange,
    decision: str,
    note: str | None,
    requested_changes: str | None = None,
) -> RecommendationChange:
    decision = decision.strip().lower()
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"Invalid decision: {decision}")

    now = datetime.now(timezone.utc)
    recommendation.status = decision
    recommendation.decision_notes = note
    recommendation.requested_changes = requested_changes
    recommendation.decided_at = now

    if decision == "approved":
        proposed = recommendation.proposed_workout or {}
        target_id = recommendation.planned_workout_id
        workout_id = target_id or _parse_uuid(proposed.get("workout_id"))
        target = await _find_target_workout(
            db,
            workout_id=workout_id,
            workout_date=recommendation.workout_date,
            discipline=_normalise_discipline(proposed.get("discipline")),
        )

        before_snapshot = _workout_snapshot(target)
        if target and proposed:
            _apply_proposed_workout(target, proposed)
            recommendation.planned_workout_id = target.id
        after_snapshot = _workout_snapshot(target)

        payload = fallback_writeback_payload(
            workout_date=(target.date.isoformat() if target and target.date else recommendation.workout_date.isoformat() if recommendation.workout_date else proposed.get("workout_date")),
            discipline=(target.discipline if target else proposed.get("discipline")),
            workout_type=(target.workout_type if target else proposed.get("workout_type")),
            target_duration=(target.target_duration if target else _coerce_int(proposed.get("target_duration"))),
            description=(target.description if target else proposed.get("description")),
            recommendation_text=recommendation.recommendation_text,
        )
        recommendation.garmin_sync_payload = payload
        writeback = await write_recommendation_change(payload)
        refresh_result: dict[str, Any] | None = None
        if str(writeback.get("status", "")).lower() == "success":
            # Force a calendar pull so app tables reflect the approved change quickly.
            refresh_result = await refresh_garmin_daily_data_on_demand(
                include_calendar=True,
                force=True,
            )
            if isinstance(refresh_result, dict):
                writeback = {**writeback, "calendar_refresh": refresh_result}
        recommendation.garmin_sync_result = writeback
        recommendation.garmin_sync_status = str(writeback.get("status", "failed"))
        recommendation.applied_at = now

        _append_event(
            recommendation,
            event="approved",
            payload={
                "note": note,
                "before": before_snapshot,
                "after": after_snapshot,
                "garmin": {
                    "status": recommendation.garmin_sync_status,
                    "result": writeback,
                    "calendar_refresh": refresh_result,
                },
            },
        )
    elif decision == "rejected":
        recommendation.garmin_sync_status = "skipped"
        _append_event(
            recommendation,
            event="rejected",
            payload={"note": note},
        )
    else:
        recommendation.garmin_sync_status = "skipped"
        _append_event(
            recommendation,
            event="changes_requested",
            payload={
                "note": note,
                "requested_changes": requested_changes,
            },
        )

    await db.flush()
    return recommendation
